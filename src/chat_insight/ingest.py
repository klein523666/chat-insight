from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import Account, Message, Source, now_ms
from .schemas import UnifiedMessage


def fallback_hash(message: UnifiedMessage) -> str | None:
    if message.external_message_id:
        return None
    canonical = json.dumps(
        [
            message.platform,
            message.account_id,
            message.external_chat_id,
            message.sender_id,
            message.timestamp,
            message.text,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(slots=True)
class BatchResult:
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "accepted": self.accepted,
            "duplicate": self.duplicate,
            "rejected": self.rejected,
        }


@dataclass(slots=True)
class Envelope:
    messages: list[UnifiedMessage]
    future: asyncio.Future[BatchResult]


class MessageWriter:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue(maxsize=200)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="message-writer")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)

    async def submit(self, messages: list[UnifiedMessage]) -> BatchResult:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[BatchResult] = loop.create_future()
        self._queue.put_nowait(Envelope(messages, future))
        return await future

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            envelopes = [first]
            count = len(first.messages)
            deadline = asyncio.get_running_loop().time() + 0.2
            while count < 500:
                timeout = deadline - asyncio.get_running_loop().time()
                if timeout <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout)
                except TimeoutError:
                    break
                envelopes.append(item)
                count += len(item.messages)
            try:
                results = await self._write(envelopes)
                for envelope, result in zip(envelopes, results, strict=True):
                    if not envelope.future.cancelled():
                        envelope.future.set_result(result)
            except Exception as exc:
                for envelope in envelopes:
                    if not envelope.future.cancelled():
                        envelope.future.set_exception(exc)
            finally:
                for _ in envelopes:
                    self._queue.task_done()

    async def _write(self, envelopes: list[Envelope]) -> list[BatchResult]:
        results = [BatchResult() for _ in envelopes]
        async with self._sessions() as session:
            for envelope, result in zip(envelopes, results, strict=True):
                for payload in envelope.messages:
                    source = await session.scalar(
                        select(Source)
                        .join(Account, Account.id == Source.account_id)
                        .where(
                            Source.platform == payload.platform,
                            Account.external_account_id == payload.account_id,
                            Source.external_chat_id == payload.external_chat_id,
                        )
                    )
                    if not source or not source.enabled or payload.chat_type == "private":
                        result.rejected += 1
                        continue
                    row = Message(
                        platform=payload.platform,
                        account_external_id=payload.account_id,
                        source_id=source.id,
                        external_chat_id=payload.external_chat_id,
                        chat_type=payload.chat_type,
                        chat_title=payload.chat_title or source.title,
                        external_message_id=payload.external_message_id,
                        fallback_hash=fallback_hash(payload),
                        sender_id=payload.sender_id,
                        sender_name=payload.sender_name,
                        sender_username=payload.sender_username,
                        timestamp=payload.timestamp,
                        text=payload.text,
                        raw_content=payload.raw_content,
                        reply_to_message_id=payload.reply_to_message_id,
                        message_type=payload.message_type,
                        is_outgoing=payload.is_outgoing,
                        is_bot=payload.is_bot,
                        metadata_json=payload.metadata,
                    )
                    try:
                        async with session.begin_nested():
                            session.add(row)
                            await session.flush()
                        result.accepted += 1
                    except IntegrityError:
                        result.duplicate += 1
                    source.last_seen_at = max(source.last_seen_at, payload.timestamp)
            await session.commit()
        return results


async def upsert_source(session: AsyncSession, payload: Any) -> Source:
    account = await session.scalar(
        select(Account).where(
            Account.platform == payload.platform,
            Account.external_account_id == payload.external_account_id,
        )
    )
    if not account:
        account = Account(
            platform=payload.platform,
            external_account_id=payload.external_account_id,
            display_name=payload.account_display_name,
            status="online",
            last_seen_at=now_ms(),
        )
        session.add(account)
        await session.flush()
    else:
        account.display_name = payload.account_display_name or account.display_name
        account.status = "online"
        account.last_seen_at = now_ms()
    source = await session.scalar(
        select(Source).where(
            Source.account_id == account.id,
            Source.external_chat_id == payload.external_chat_id,
        )
    )
    if not source:
        source = Source(
            platform=payload.platform,
            account_id=account.id,
            source_type=payload.source_type,
            chat_type=payload.chat_type,
            external_chat_id=payload.external_chat_id,
            title=payload.title,
            username=payload.username,
            enabled=False,
            status=payload.status,
            metadata_json=payload.metadata,
        )
        session.add(source)
    else:
        source.chat_type = payload.chat_type
        source.title = payload.title or source.title
        source.username = payload.username
        source.status = payload.status
        source.last_seen_at = now_ms()
        source.metadata_json = payload.metadata
    if payload.status == "migrated":
        source.enabled = False
    return source
