from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .ai import OpenAICompatibleClient
from .config import Settings
from .database import close_database, create_database, upgrade_database
from .feishu import send_feishu
from .ingest import BatchResult, MessageWriter, upsert_source
from .models import (
    Account,
    AdminUser,
    AIProvider,
    CollectorState,
    DeliveryTarget,
    Message,
    Report,
    ReportRun,
    ReportTask,
    Source,
    TelegramCredential,
    WebSession,
    now_ms,
)
from .reports import ReportService
from .scheduler import SchedulerService
from .schemas import (
    AIProviderInput,
    DeliveryTargetInput,
    HeartbeatRequest,
    LoginRequest,
    MessageBatch,
    ReportTaskInput,
    SetupRequest,
    SourceBulkPatch,
    SourcePatch,
    SourceUpsert,
    TelegramConfigInput,
    TelegramValueInput,
)
from .security import (
    SecretBox,
    constant_time_equal,
    hash_password,
    mask_secret,
    token,
    token_hash,
    verify_password,
)

SESSION_COOKIE = "chat_insight_session"
SESSION_AGE_MS = int(timedelta(days=7).total_seconds() * 1000)


def _source_dict(item: Source) -> dict[str, Any]:
    return {
        "id": item.id,
        "platform": item.platform,
        "account_id": item.account_id,
        "chat_type": item.chat_type,
        "external_chat_id": item.external_chat_id,
        "title": item.title,
        "username": item.username,
        "enabled": item.enabled,
        "report_enabled": item.report_enabled,
        "status": item.status,
        "last_seen_at": item.last_seen_at,
        "folders": item.metadata_json.get("telegram_folders", []),
    }


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


async def web_session(request: Request, session: AsyncSession = Depends(db_session)) -> WebSession:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    row = await session.scalar(
        select(WebSession).where(
            WebSession.token_hash == token_hash(raw), WebSession.expires_at > now_ms()
        )
    )
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return row


async def csrf(request: Request, current: WebSession = Depends(web_session)) -> WebSession:
    if not constant_time_equal(request.headers.get("X-CSRF-Token"), current.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
    return current


async def internal_auth(request: Request) -> None:
    expected = request.app.state.settings.collector_token
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not expected or not constant_time_equal(supplied, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid collector token")


async def _telegram(request: Request, path: str, payload: dict[str, Any] | None = None) -> Any:
    settings: Settings = request.app.state.settings
    if not settings.collector_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Collector token is not configured"
        )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(
                "POST" if payload is not None else "GET",
                f"{settings.telegram_collector_url}{path}",
                headers={"Authorization": f"Bearer {settings.collector_token}"},
                json=payload,
            )
            if response.status_code == status.HTTP_409_CONFLICT:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Telegram 尚未配置，请先保存 API ID 和 API Hash",
                )
            if response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    (
                        "Telegram 拒绝二维码登录，请核对 API ID 和 API Hash"
                        if path.endswith("/qr")
                        else "Telegram 拒绝此登录步骤，请刷新状态后重试"
                    ),
                )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram collector unavailable"
        ) from exc


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await upgrade_database(app_settings)
        engine, sessions = create_database(app_settings)
        secrets = SecretBox(app_settings.master_key)
        writer = MessageWriter(sessions)
        reports = ReportService(sessions, secrets)
        scheduler = SchedulerService(sessions, reports)
        app.state.settings = app_settings
        app.state.engine = engine
        app.state.sessions = sessions
        app.state.secrets = secrets
        app.state.writer = writer
        app.state.reports = reports
        app.state.scheduler = scheduler
        writer.start()
        await scheduler.start()
        try:
            yield
        finally:
            scheduler.stop()
            await writer.stop()
            await close_database(engine)

    app = FastAPI(title="Chat Insight", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/v1/setup/status")
    async def setup_status(session: AsyncSession = Depends(db_session)) -> dict[str, bool]:
        return {"required": (await session.scalar(select(func.count(AdminUser.id)))) == 0}

    @app.post("/api/v1/setup", status_code=201)
    async def setup(
        payload: SetupRequest, request: Request, session: AsyncSession = Depends(db_session)
    ) -> dict[str, str]:
        if await session.scalar(select(func.count(AdminUser.id))):
            raise HTTPException(status.HTTP_409_CONFLICT, "Setup is already complete")
        if not constant_time_equal(payload.setup_token, request.app.state.settings.setup_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid setup token")
        session.add(
            AdminUser(
                id=1,
                username=payload.username,
                password_hash=hash_password(payload.password),
            )
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "Setup is already complete") from exc
        return {"status": "created"}

    @app.post("/api/v1/auth/login")
    async def login(
        payload: LoginRequest, response: Response, session: AsyncSession = Depends(db_session)
    ) -> dict[str, Any]:
        user = await session.scalar(select(AdminUser).where(AdminUser.username == payload.username))
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        raw, csrf_value = token(), token()
        session.add(
            WebSession(
                user_id=user.id,
                token_hash=token_hash(raw),
                csrf_token=csrf_value,
                expires_at=now_ms() + SESSION_AGE_MS,
            )
        )
        await session.commit()
        response.set_cookie(
            SESSION_COOKIE,
            raw,
            max_age=SESSION_AGE_MS // 1000,
            httponly=True,
            secure=app_settings.cookie_secure,
            samesite="lax",
        )
        return {"username": user.username, "csrf_token": csrf_value}

    @app.get("/api/v1/auth/me")
    async def me(
        current: WebSession = Depends(web_session), session: AsyncSession = Depends(db_session)
    ) -> dict[str, Any]:
        user = await session.get(AdminUser, current.user_id)
        return {"username": user.username if user else "", "csrf_token": current.csrf_token}

    @app.post("/api/v1/auth/logout")
    async def logout(
        response: Response,
        current: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        await session.delete(current)
        await session.commit()
        response.delete_cookie(SESSION_COOKIE)
        return {"status": "logged_out"}

    @app.get("/api/v1/accounts")
    async def accounts(
        _: WebSession = Depends(web_session), session: AsyncSession = Depends(db_session)
    ) -> list[dict[str, Any]]:
        rows = (await session.scalars(select(Account).order_by(Account.platform))).all()
        return [
            {
                "id": row.id,
                "platform": row.platform,
                "display_name": row.display_name,
                "external_account_id": row.external_account_id,
                "status": row.status,
                "last_seen_at": row.last_seen_at,
            }
            for row in rows
        ]

    @app.get("/api/v1/sources")
    async def sources(
        platform: str | None = None,
        search: str | None = None,
        _: WebSession = Depends(web_session),
        session: AsyncSession = Depends(db_session),
    ) -> list[dict[str, Any]]:
        query = select(Source).order_by(Source.platform, Source.title)
        if platform:
            query = query.where(Source.platform == platform)
        if search:
            query = query.where(Source.title.contains(search))
        return [_source_dict(row) for row in (await session.scalars(query)).all()]

    @app.patch("/api/v1/sources/{source_id}")
    async def patch_source(
        source_id: int,
        payload: SourcePatch,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        row = await session.get(Source, source_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
        if payload.enabled and row.status == "migrated":
            raise HTTPException(status.HTTP_409_CONFLICT, "Migrated source cannot be enabled")
        if payload.enabled is not None:
            row.enabled = payload.enabled
        if payload.report_enabled is not None:
            row.report_enabled = payload.report_enabled
        await session.commit()
        return _source_dict(row)

    @app.patch("/api/v1/sources:batch")
    async def patch_sources(
        payload: SourceBulkPatch,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, list[dict[str, Any]]]:
        source_ids = set(payload.source_ids)
        rows = (
            await session.scalars(select(Source).where(Source.id.in_(source_ids)))
        ).all()
        if len(rows) != len(source_ids):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
        if payload.enabled and any(row.status == "migrated" for row in rows):
            raise HTTPException(status.HTTP_409_CONFLICT, "Migrated source cannot be enabled")
        for row in rows:
            row.enabled = payload.enabled
        await session.commit()
        return {"sources": [_source_dict(row) for row in rows]}

    @app.post("/internal/v1/sources:upsert", dependencies=[Depends(internal_auth)])
    async def internal_sources(
        payloads: list[SourceUpsert], session: AsyncSession = Depends(db_session)
    ) -> dict[str, Any]:
        if len(payloads) > 1000:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Too many sources")
        rows = [await upsert_source(session, payload) for payload in payloads]
        await session.commit()
        return {"sources": [_source_dict(row) for row in rows]}

    @app.get("/internal/v1/sources/enabled", dependencies=[Depends(internal_auth)])
    async def enabled_sources(
        platform: str = Query(min_length=1),
        account_id: str = Query(min_length=1),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, list[str]]:
        rows = (
            await session.scalars(
                select(Source.external_chat_id)
                .join(Account)
                .where(
                    Source.platform == platform,
                    Account.external_account_id == account_id,
                    Source.enabled.is_(True),
                    Source.status == "online",
                )
            )
        ).all()
        return {"external_chat_ids": list(rows)}

    @app.post("/internal/v1/messages:batch", dependencies=[Depends(internal_auth)])
    async def messages_batch(payload: MessageBatch, request: Request) -> dict[str, int]:
        try:
            result = cast(BatchResult, await request.app.state.writer.submit(payload.messages))
        except asyncio.QueueFull as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Message queue is full"
            ) from exc
        return result.as_dict()

    @app.post("/internal/v1/collectors/heartbeat", dependencies=[Depends(internal_auth)])
    async def heartbeat(
        payload: HeartbeatRequest, session: AsyncSession = Depends(db_session)
    ) -> dict[str, str]:
        row = await session.get(CollectorState, payload.collector_id)
        if not row:
            row = CollectorState(collector_id=payload.collector_id, platform=payload.platform)
            session.add(row)
        row.status = payload.status
        row.detail_json = payload.detail
        row.last_seen_at = now_ms()
        await session.commit()
        return {"status": "ok"}

    @app.get("/internal/v1/telegram/config", dependencies=[Depends(internal_auth)])
    async def internal_telegram_config(
        request: Request, session: AsyncSession = Depends(db_session)
    ) -> dict[str, Any]:
        row = await session.scalar(select(TelegramCredential).limit(1))
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram is not configured")
        return {
            "api_id": row.api_id,
            "api_hash": request.app.state.secrets.decrypt(row.api_hash_encrypted),
        }

    @app.put("/api/v1/telegram/config")
    async def telegram_config(
        payload: TelegramConfigInput,
        request: Request,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        row = await session.scalar(select(TelegramCredential).limit(1))
        encrypted = request.app.state.secrets.encrypt(payload.api_hash)
        if row:
            row.api_id, row.api_hash_encrypted, row.updated_at = payload.api_id, encrypted, now_ms()
        else:
            session.add(TelegramCredential(api_id=payload.api_id, api_hash_encrypted=encrypted))
        await session.commit()
        await _telegram(request, "/internal/configure", payload.model_dump())
        return {"status": "configured", "api_hash": mask_secret(payload.api_hash) or ""}

    @app.get("/api/v1/telegram/auth/status")
    async def telegram_status(request: Request, _: WebSession = Depends(web_session)) -> Any:
        return await _telegram(request, "/internal/status")

    @app.post("/api/v1/telegram/auth/qr")
    async def telegram_qr(request: Request, _: WebSession = Depends(csrf)) -> Any:
        return await _telegram(request, "/internal/auth/qr", {})

    @app.post("/api/v1/telegram/auth/logout")
    async def telegram_logout(request: Request, _: WebSession = Depends(csrf)) -> Any:
        return await _telegram(request, "/internal/auth/logout", {})

    def telegram_value_handler(action: str) -> Any:
        async def value_handler(
            payload: TelegramValueInput,
            request: Request,
            _: WebSession = Depends(csrf),
        ) -> Any:
            return await _telegram(request, f"/internal/auth/{action}", payload.model_dump())

        return value_handler

    for route, action in [
        ("phone", "phone"),
        ("code", "code"),
        ("password", "password"),
        ("email", "email"),
        ("email-code", "email-code"),
    ]:
        app.add_api_route(
            f"/api/v1/telegram/auth/{route}",
            telegram_value_handler(action),
            methods=["POST"],
        )

    @app.put("/api/v1/settings/ai")
    async def put_ai(
        payload: AIProviderInput,
        request: Request,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        row = await session.scalar(select(AIProvider).limit(1))
        if not row:
            row = AIProvider()
            session.add(row)
        row.enabled, row.base_url, row.model = payload.enabled, payload.base_url, payload.model
        row.max_input_chars, row.updated_at = payload.max_input_chars, now_ms()
        if payload.api_key:
            row.api_key_encrypted = request.app.state.secrets.encrypt(payload.api_key)
        if not row.api_key_encrypted:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "API key is required")
        await session.commit()
        return {
            "enabled": row.enabled,
            "base_url": row.base_url,
            "model": row.model,
            "api_key": "********",
        }

    @app.get("/api/v1/settings/ai")
    async def get_ai(
        _: WebSession = Depends(web_session), session: AsyncSession = Depends(db_session)
    ) -> dict[str, Any]:
        row = await session.scalar(select(AIProvider).limit(1))
        return (
            {"configured": False}
            if not row
            else {
                "configured": True,
                "enabled": row.enabled,
                "base_url": row.base_url,
                "model": row.model,
                "api_key": "********",
            }
        )

    @app.post("/api/v1/settings/ai/test")
    async def test_ai(
        request: Request, _: WebSession = Depends(csrf), session: AsyncSession = Depends(db_session)
    ) -> dict[str, str]:
        row = await session.scalar(select(AIProvider).where(AIProvider.enabled.is_(True)))
        if not row or not row.api_key_encrypted:
            raise HTTPException(status.HTTP_409_CONFLICT, "AI is not configured")
        client = OpenAICompatibleClient(
            row.base_url, request.app.state.secrets.decrypt(row.api_key_encrypted) or "", row.model
        )
        await client.test()
        return {"status": "ok"}

    @app.get("/api/v1/delivery-targets")
    async def list_targets(
        _: WebSession = Depends(web_session), session: AsyncSession = Depends(db_session)
    ) -> list[dict[str, Any]]:
        rows = (await session.scalars(select(DeliveryTarget).order_by(DeliveryTarget.name))).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "enabled": row.enabled,
                "type": row.target_type,
                "webhook": "********",
            }
            for row in rows
        ]

    @app.post("/api/v1/delivery-targets", status_code=201)
    async def create_target(
        payload: DeliveryTargetInput,
        request: Request,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        row = DeliveryTarget(
            name=payload.name,
            enabled=payload.enabled,
            webhook_encrypted=request.app.state.secrets.encrypt(str(payload.webhook)),
            secret_encrypted=request.app.state.secrets.encrypt(payload.secret)
            if payload.secret
            else None,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return {"id": row.id, "name": row.name, "enabled": row.enabled}

    @app.delete("/api/v1/delivery-targets/{target_id}")
    async def delete_target(
        target_id: int,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, str]:
        row = await session.get(DeliveryTarget, target_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
        await session.delete(row)
        await session.commit()
        return {"status": "deleted"}

    @app.post("/api/v1/delivery-targets/{target_id}/test")
    async def test_target(
        target_id: int,
        request: Request,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        row = await session.get(DeliveryTarget, target_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
        result = await send_feishu(
            request.app.state.secrets.decrypt(row.webhook_encrypted) or "",
            request.app.state.secrets.decrypt(row.secret_encrypted),
            "Chat Insight 测试",
            "连接成功。",
        )
        return {"success": result.success, "status_code": result.status_code, "error": result.error}

    @app.get("/api/v1/report-tasks")
    async def list_tasks(
        _: WebSession = Depends(web_session), session: AsyncSession = Depends(db_session)
    ) -> list[dict[str, Any]]:
        rows = (
            await session.scalars(
                select(ReportTask).options(
                    selectinload(ReportTask.sources), selectinload(ReportTask.delivery_targets)
                )
            )
        ).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "enabled": row.enabled,
                "schedule_type": row.schedule_type,
                "schedule_hour": row.schedule_hour,
                "schedule_minute": row.schedule_minute,
                "timezone": row.timezone,
                "source_ids": [x.id for x in row.sources],
                "delivery_target_ids": [x.id for x in row.delivery_targets],
            }
            for row in rows
        ]

    async def save_task(
        task: ReportTask, payload: ReportTaskInput, session: AsyncSession
    ) -> ReportTask:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(payload.timezone)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown timezone") from exc
        selected_sources = list(
            (
                await session.scalars(
                    select(Source).where(
                        Source.id.in_(payload.source_ids),
                        Source.enabled.is_(True),
                        Source.report_enabled.is_(True),
                    )
                )
            ).all()
        )
        if len(selected_sources) != len(set(payload.source_ids)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown source")
        targets = list(
            (
                await session.scalars(
                    select(DeliveryTarget).where(DeliveryTarget.id.in_(payload.delivery_target_ids))
                )
            ).all()
        )
        task.name, task.enabled, task.schedule_type = (
            payload.name,
            payload.enabled,
            payload.schedule_type,
        )
        task.schedule_hour, task.schedule_minute, task.timezone = (
            payload.schedule_hour,
            payload.schedule_minute,
            payload.timezone,
        )
        task.window_type = (
            "previous_complete_hour" if payload.schedule_type == "hourly" else "today_to_fire"
        )
        task.sources, task.delivery_targets, task.updated_at = selected_sources, targets, now_ms()
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task

    @app.post("/api/v1/report-tasks", status_code=201)
    async def create_task(
        payload: ReportTaskInput,
        request: Request,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        row = await save_task(ReportTask(), payload, session)
        request.app.state.scheduler.sync(row)
        return {"id": row.id, "name": row.name}

    @app.put("/api/v1/report-tasks/{task_id}")
    async def update_task(
        task_id: int,
        payload: ReportTaskInput,
        request: Request,
        _: WebSession = Depends(csrf),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        row = await session.get(ReportTask, task_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
        row = await save_task(row, payload, session)
        request.app.state.scheduler.sync(row)
        return {"id": row.id, "name": row.name}

    @app.post("/api/v1/report-tasks/{task_id}/run")
    async def run_task(
        task_id: int,
        request: Request,
        deliver: bool = False,
        _: WebSession = Depends(csrf),
    ) -> dict[str, Any]:
        try:
            report = await request.app.state.reports.run(task_id, deliver=deliver)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return {"report_id": report.id, "title": report.title}

    @app.get("/api/v1/reports")
    async def list_reports(
        _: WebSession = Depends(web_session), session: AsyncSession = Depends(db_session)
    ) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(Report, ReportRun)
                .join(ReportRun, ReportRun.id == Report.run_id)
                .order_by(Report.created_at.desc())
                .limit(100)
            )
        ).all()
        return [
            {
                "id": report.id,
                "title": report.title,
                "created_at": report.created_at,
                "message_count": run.message_count,
                "ai_status": run.ai_status,
            }
            for report, run in rows
        ]

    @app.get("/api/v1/reports/{report_id}")
    async def get_report(
        report_id: int,
        _: WebSession = Depends(web_session),
        session: AsyncSession = Depends(db_session),
    ) -> dict[str, Any]:
        row = await session.get(Report, report_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
        return {
            "id": row.id,
            "title": row.title,
            "markdown": row.markdown,
            "structured": row.structured_json,
            "created_at": row.created_at,
        }

    @app.get("/api/v1/system/status")
    async def system_status(
        _: WebSession = Depends(web_session), session: AsyncSession = Depends(db_session)
    ) -> dict[str, Any]:
        collectors = (await session.scalars(select(CollectorState))).all()
        return {
            "core": "healthy",
            "collectors": [
                {
                    "id": row.collector_id,
                    "platform": row.platform,
                    "status": row.status,
                    "last_seen_at": row.last_seen_at,
                }
                for row in collectors
            ],
            "counts": {
                "accounts": await session.scalar(select(func.count(Account.id))),
                "sources": await session.scalar(select(func.count(Source.id))),
                "enabled_sources": await session.scalar(
                    select(func.count(Source.id)).where(Source.enabled.is_(True))
                ),
                "reports": await session.scalar(select(func.count(Report.id))),
                "messages": await session.scalar(select(func.count(Message.id))),
            },
        }

    web_dist = Path(os.getenv("CHAT_INSIGHT_WEB_DIST", Path.cwd() / "apps" / "web" / "dist"))
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    @app.exception_handler(RuntimeError)
    async def runtime_error(_: Request, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    return app
