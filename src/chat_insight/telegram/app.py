from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel

from chat_insight.security import constant_time_equal

from .service import (
    CollectorSettings,
    TelegramAuthenticationError,
    TelegramCollector,
    TelegramNotConfiguredError,
)


class ConfigureRequest(BaseModel):
    api_id: int
    api_hash: str


class ValueRequest(BaseModel):
    value: str


async def auth(request: Request) -> None:
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not constant_time_equal(supplied, request.app.state.settings.collector_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid collector token")


def create_app(settings: CollectorSettings | None = None) -> FastAPI:
    collector_settings = settings or CollectorSettings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        collector = TelegramCollector(collector_settings)
        app.state.settings = collector_settings
        app.state.collector = collector
        await collector.start()
        try:
            yield
        finally:
            await collector.close()

    app = FastAPI(title="Chat Insight Telegram Collector", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/configure", dependencies=[Depends(auth)])
    async def configure(payload: ConfigureRequest, request: Request) -> dict[str, str]:
        await request.app.state.collector.configure(payload.api_id, payload.api_hash)
        return {"status": "configured"}

    @app.get("/internal/status", dependencies=[Depends(auth)])
    async def collector_status(request: Request) -> dict[str, Any]:
        collector = request.app.state.collector
        state = collector.state
        return {
            "authorization_state": state.authorization_state,
            "qr_link": state.qr_link,
            "account_id": state.account_id,
            "username": state.username,
            "display_name": state.display_name,
            "chat_count": state.chat_count,
            "last_error": state.last_error,
            "diagnostics": {
                "enabled_source_count": len(collector.enabled),
                "outgoing_queue_size": collector.outgoing.qsize(),
                "new_message_updates": state.new_message_updates,
                "messages_dropped_unknown_chat": state.messages_dropped_unknown_chat,
                "messages_dropped_disabled": state.messages_dropped_disabled,
                "messages_queued": state.messages_queued,
                "backfill_requests": state.backfill_requests,
                "backfill_messages": state.backfill_messages,
                "backfill_errors": state.backfill_errors,
                "basic_group_count": len(collector.basic_groups),
                "upgraded_basic_group_count": sum(
                    bool(group.get("upgraded_to_supergroup_id"))
                    for group in collector.basic_groups.values()
                ),
            },
        }

    @app.post("/internal/auth/qr", dependencies=[Depends(auth)])
    async def qr(request: Request) -> dict[str, str]:
        try:
            await request.app.state.collector.auth("qr")
        except TelegramNotConfiguredError as exc:
            # QR 登录必须先由 Core 保存 Telegram API 凭据；不要把此类可预期状态记为 500。
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Telegram 尚未配置，请先保存 API ID 和 API Hash",
            ) from exc
        except TelegramAuthenticationError as exc:
            message = (
                "二维码已失效，请重新生成后立即扫描"
                if str(exc) == "AUTH_TOKEN_INVALID"
                else "Telegram 拒绝二维码登录，请核对 API ID 和 API Hash"
            )
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                message,
            ) from exc
        return {"status": "waiting"}

    @app.post("/internal/auth/logout", dependencies=[Depends(auth)])
    async def logout(request: Request) -> dict[str, str]:
        await request.app.state.collector.auth("logout")
        return {"status": "logging_out"}

    def value_handler(action: str) -> Any:
        async def handler(payload: ValueRequest, request: Request) -> dict[str, str]:
            try:
                await request.app.state.collector.auth(action, payload.value)
            except TelegramNotConfiguredError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Telegram 尚未配置，请先保存 API ID 和 API Hash",
                ) from exc
            except TelegramAuthenticationError as exc:
                message = (
                    "当前正在等待二维码确认，请刷新后再选择登录方式"
                    if action == "phone"
                    else "Telegram 拒绝此登录步骤，请刷新状态后重试"
                )
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message) from exc
            return {"status": "submitted"}

        return handler

    for route in ["phone", "code", "password", "email", "email-code"]:
        app.add_api_route(
            f"/internal/auth/{route}",
            value_handler(route),
            methods=["POST"],
            dependencies=[Depends(auth)],
        )
    return app


def run() -> None:
    uvicorn.run("chat_insight.telegram.app:create_app", factory=True, host="0.0.0.0", port=8090)


if __name__ == "__main__":
    run()
