from __future__ import annotations

import asyncio
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .ai import DEFAULT_REPORT_PROMPT, AIResponseError, OpenAICompatibleClient
from .feishu import send_feishu
from .models import (
    AIProvider,
    DeliveryLog,
    Message,
    Report,
    ReportRun,
    ReportTask,
    now_ms,
)
from .schemas import AIAnalysis
from .security import SecretBox

WORD = re.compile(r"[\w\u4e00-\u9fff]{2,}")
STOP_WORDS = {"这个", "那个", "我们", "你们", "他们", "可以", "就是", "还是", "没有", "什么"}


def report_window(task: ReportTask, now: datetime | None = None) -> tuple[int, int]:
    try:
        zone = ZoneInfo(task.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {task.timezone}") from exc
    local = (now or datetime.now(UTC)).astimezone(zone)
    if task.schedule_type == "hourly":
        end = local.replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=1)
    else:
        end = local.replace(
            hour=task.schedule_hour,
            minute=task.schedule_minute,
            second=0,
            microsecond=0,
        )
        if local < end:
            end -= timedelta(days=1)
        start = end.replace(hour=0, minute=0)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def statistics(messages: list[Message]) -> dict[str, Any]:
    sources = Counter(message.chat_title or message.external_chat_id for message in messages)
    platforms = Counter(message.platform for message in messages)
    users = Counter(
        message.sender_name or message.sender_username or "匿名"
        for message in messages
        if message.chat_type != "channel" and not message.is_bot
    )
    words = Counter(
        word.lower()
        for message in messages
        for word in WORD.findall(message.text)
        if word.lower() not in STOP_WORDS and not word.isdigit()
    )
    return {
        "message_count": len(messages),
        "source_count": len(sources),
        "platforms": dict(platforms),
        "top_sources": sources.most_common(10),
        "top_users": users.most_common(10),
        "keywords": words.most_common(20),
    }


def _finding_lines(title: str, values: list[Any]) -> list[str]:
    if not values:
        return []
    return [f"\n## {title}", *[f"- {item.text}" for item in values]]


def render_markdown(title: str, stats: dict[str, Any], ai: AIAnalysis | None) -> str:
    platform_summary = ", ".join(f"{key} {value}" for key, value in stats["platforms"].items())
    lines = [
        f"# {title}",
        "",
        f"- 消息：**{stats['message_count']}**",
        f"- 来源：**{stats['source_count']}**",
        f"- 平台：{platform_summary or '无'}",
        "",
        "## 活跃来源",
        *[f"- {name}：{count}" for name, count in stats["top_sources"]],
        "",
        "## 关键词",
        *[f"- {word}：{count}" for word, count in stats["keywords"][:12]],
    ]
    if ai:
        lines.extend(["", "## AI 总结", ai.summary or ai.conclusion])
        if ai.topics:
            lines.extend(["", "## 热门话题", *[f"- **{x.title}**：{x.summary}" for x in ai.topics]])
        lines.extend(_finding_lines("用户需求", ai.user_needs))
        lines.extend(_finding_lines("问题与风险", [*ai.problems, *ai.risks]))
        lines.extend(_finding_lines("潜在线索", ai.opportunities))
        lines.extend(_finding_lines("待跟进", ai.todos))
    return "\n".join(lines).strip() + "\n"


class ReportService:
    def __init__(self, sessions: Any, secrets: SecretBox) -> None:
        self.sessions = sessions
        self.secrets = secrets
        # ponytail: 单进程全局串行足以保护 SQLite；需要并行报告时再改为数据库级协调。
        self._run_lock = asyncio.Lock()

    async def run(
        self,
        task_id: int,
        deliver: bool = True,
        window: tuple[int, int] | None = None,
    ) -> Report:
        async with self._run_lock:
            return await self._run(task_id, deliver, window)

    async def _run(
        self,
        task_id: int,
        deliver: bool,
        window: tuple[int, int] | None,
    ) -> Report:
        async with self.sessions() as session:
            task = await session.scalar(
                select(ReportTask)
                .options(
                    selectinload(ReportTask.sources), selectinload(ReportTask.delivery_targets)
                )
                .where(ReportTask.id == task_id)
            )
            if not task:
                raise LookupError("Report task not found")
            start, end = window or report_window(task)
            existing = await session.scalar(
                select(ReportRun).where(
                    ReportRun.task_id == task.id,
                    ReportRun.window_start == start,
                    ReportRun.window_end == end,
                )
            )
            if existing:
                report = await session.scalar(select(Report).where(Report.run_id == existing.id))
                if report:
                    targets = list(task.delivery_targets)
                    title, markdown = report.title, report.markdown
                    if deliver:
                        await self._deliver(report, title, markdown, targets)
                    return cast(Report, report)
                raise RuntimeError("Report window is already running")
            run = ReportRun(
                task_id=task.id,
                window_start=start,
                window_end=end,
                started_at=now_ms(),
            )
            source_ids = [item.id for item in task.sources]
            messages = list(
                (
                    await session.scalars(
                        select(Message)
                        .where(
                            Message.source_id.in_(source_ids),
                            Message.timestamp >= start,
                            Message.timestamp < end,
                        )
                        .order_by(Message.timestamp)
                    )
                ).all()
            )
            stats = statistics(messages)
            run.message_count = stats["message_count"]
            run.source_count = stats["source_count"]
            ai: AIAnalysis | None = None
            provider = await session.scalar(select(AIProvider).where(AIProvider.enabled.is_(True)))
            if provider and provider.api_key_encrypted and messages:
                try:
                    client = OpenAICompatibleClient(
                        provider.base_url,
                        self.secrets.decrypt(provider.api_key_encrypted) or "",
                        provider.model,
                    )
                    current_prompt = task.report_prompt.strip() or DEFAULT_REPORT_PROMPT
                    ai = await client.analyze(messages, provider.max_input_chars, current_prompt)
                    by_id = {message.id: message for message in messages}
                    allowed = set(by_id)
                    for topic in ai.topics:
                        topic.evidence_message_ids = [
                            value for value in topic.evidence_message_ids if value in allowed
                        ]
                    finding_groups = [
                        *ai.important_events,
                        *ai.user_needs,
                        *ai.problems,
                        *ai.risks,
                        *ai.opportunities,
                        *ai.todos,
                        *ai.important_quotes,
                        *ai.trends,
                    ]
                    for finding in finding_groups:
                        finding.evidence_message_ids = [
                            value for value in finding.evidence_message_ids if value in allowed
                        ]
                    ai.important_quotes = [
                        quote for quote in ai.important_quotes if quote.evidence_message_ids
                    ]
                    for quote in ai.important_quotes:
                        quote.text = by_id[quote.evidence_message_ids[0]].text
                    run.ai_status = "success"
                    if task.prompt_mode == "adaptive":
                        try:
                            next_prompt = await client.refine_report_prompt(
                                current_prompt, messages, provider.max_input_chars
                            )
                            if next_prompt:
                                task.report_prompt = next_prompt
                                task.updated_at = now_ms()
                        except AIResponseError:
                            pass
                except Exception as exc:
                    run.ai_status = "fallback"
                    code = exc.code if isinstance(exc, AIResponseError) else type(exc).__name__
                    run.error = f"AI fallback: {code}"
            local_end = datetime.fromtimestamp(end / 1000, UTC).astimezone(ZoneInfo(task.timezone))
            title = f"{task.name} · {local_end:%Y-%m-%d %H:%M}"
            markdown = render_markdown(title, stats, ai)
            # AI/网络调用期间不持有 SQLite 写锁；最终结果用一个短事务原子落库。
            session.add(run)
            await session.flush()
            report = Report(
                run_id=run.id,
                task_id=task.id,
                title=title,
                markdown=markdown,
                structured_json={"statistics": stats, "analysis": ai.model_dump() if ai else None},
            )
            session.add(report)
            run.status = "success"
            run.finished_at = now_ms()
            await session.commit()
            await session.refresh(report)
            targets = list(task.delivery_targets)

        if deliver:
            await self._deliver(report, title, markdown, targets)
        return report

    async def _deliver(self, report: Report, title: str, markdown: str, targets: list[Any]) -> None:
        for target in targets:
            async with self.sessions() as check_session:
                delivered = await check_session.scalar(
                    select(DeliveryLog.id).where(
                        DeliveryLog.report_id == report.id,
                        DeliveryLog.target_id == target.id,
                        DeliveryLog.status == "success",
                    )
                )
            if delivered:
                continue
            webhook = self.secrets.decrypt(target.webhook_encrypted) or ""
            secret = self.secrets.decrypt(target.secret_encrypted)
            result = await send_feishu(webhook, secret, title, markdown)
            async with self.sessions() as log_session:
                log_session.add(
                    DeliveryLog(
                        report_id=report.id,
                        target_id=target.id,
                        status="success" if result.success else "failed",
                        attempt=result.attempts,
                        response_code=result.status_code,
                        error=result.error,
                    )
                )
                await log_session.commit()
