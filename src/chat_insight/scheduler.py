from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import delete, select

from .models import Message, ReportTask, WebSession, now_ms
from .reports import report_window

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, sessions: Any, reports: Any) -> None:
        self.sessions = sessions
        self.reports = reports
        self.scheduler = AsyncIOScheduler(job_defaults={"coalesce": True, "max_instances": 1})

    async def start(self) -> None:
        self.scheduler.start()
        async with self.sessions() as session:
            tasks = list((await session.scalars(select(ReportTask))).all())
        for task in tasks:
            self.sync(task)
        self.scheduler.add_job(
            self._cleanup,
            CronTrigger(hour=3, minute=20, timezone="UTC"),
            id="message-retention",
            replace_existing=True,
        )
        asyncio.create_task(self._cleanup(), name="initial-retention-cleanup")
        asyncio.create_task(self._catch_up(tasks), name="report-catch-up")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def sync(self, task: ReportTask) -> None:
        job_id = f"report-task-{task.id}"
        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.remove_job(job_id)
        if not task.enabled:
            return
        trigger = (
            CronTrigger(minute=task.schedule_minute, timezone=task.timezone)
            if task.schedule_type == "hourly"
            else CronTrigger(
                hour=task.schedule_hour,
                minute=task.schedule_minute,
                timezone=task.timezone,
            )
        )
        self.scheduler.add_job(
            self._run,
            trigger,
            id=job_id,
            args=[task.id],
            misfire_grace_time=3600,
            replace_existing=True,
        )

    async def _run(self, task_id: int) -> None:
        try:
            await self.reports.run(task_id, deliver=True)
        except Exception:
            # APScheduler logs the exception; the next slot must remain scheduled.
            raise

    async def _catch_up(self, tasks: list[ReportTask]) -> None:
        current = datetime.now(UTC)
        for task in tasks:
            if not task.enabled:
                continue
            step = timedelta(hours=1) if task.schedule_type == "hourly" else timedelta(days=1)
            for offset in range(2, -1, -1):
                window = report_window(task, current - step * offset)
                if window[1] <= task.created_at:
                    continue
                try:
                    await self.reports.run(task.id, deliver=True, window=window)
                except Exception as exc:
                    # A failed catch-up must not prevent other tasks or the live scheduler.
                    logger.warning(
                        "report catch-up failed task_id=%s error=%s",
                        task.id,
                        type(exc).__name__,
                    )
                    continue

    async def _cleanup(self) -> None:
        cutoff = now_ms() - 90 * 24 * 60 * 60 * 1000
        async with self.sessions() as session:
            await session.execute(delete(Message).where(Message.timestamp < cutoff))
            await session.execute(delete(WebSession).where(WebSession.expires_at < now_ms()))
            await session.commit()

    def run_soon(self, task_id: int) -> None:
        asyncio.create_task(self.reports.run(task_id, deliver=True))
