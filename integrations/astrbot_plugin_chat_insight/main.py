from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .outbox import Outbox

MEDIA = {
    "image": "[图片]",
    "record": "[语音]",
    "video": "[视频]",
    "file": "[文件]",
    "face": "[表情]",
}


def normalize_segments(segments: Any) -> tuple[str, list[dict[str, Any]], str | None]:
    if isinstance(segments, str):
        return segments, [{"type": "text", "text": segments}], None
    text: list[str] = []
    raw: list[dict[str, Any]] = []
    reply: str | None = None
    for item in segments if isinstance(segments, list) else []:
        kind = str(item.get("type", "unknown"))
        data = item.get("data", {})
        if kind == "text":
            value = str(data.get("text", ""))
        elif kind == "at":
            value = f"@{data.get('qq', '')}"
        elif kind == "reply":
            reply = str(data.get("id")) if data.get("id") is not None else None
            value = ""
        else:
            value = MEDIA.get(kind, f"[{kind}]")
        if value:
            text.append(value)
        raw.append({"type": kind, **{key: data[key] for key in ("text", "file") if key in data}})
    return " ".join(text).strip(), raw, reply


class ChatInsightQQAdapter(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None) -> None:
        super().__init__(context, config)
        config = config or {}
        self.config = config
        self.core_url = str(config.get("core_url", "http://chat-insight:8080")).rstrip("/")
        token_file = Path(str(config.get("collector_token_file", "/run/secrets/collector_token")))
        self.token = (
            token_file.read_text(encoding="utf-8").strip()
            if token_file.exists()
            else str(config.get("collector_token", ""))
        )
        self.enabled: dict[str, set[str]] = {}
        data_dir = Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_chat_insight"
        self.outbox = Outbox(data_dir / "outbox.db")
        self.tasks = [
            asyncio.create_task(self._sender(), name="chat-insight-qq-sender"),
            asyncio.create_task(self._refresh_loop(), name="chat-insight-qq-sources"),
            asyncio.create_task(self._heartbeat(), name="chat-insight-qq-heartbeat"),
        ]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def on_group_message(self, event: AstrMessageEvent) -> None:
        if not self.token:
            return
        account_id = str(event.get_self_id())
        group_id = str(event.get_group_id())
        raw_event = event.message_obj.raw_message
        raw = raw_event if isinstance(raw_event, dict) else {}
        title = str(raw.get("group_name") or group_id)
        await self._upsert_sources(
            account_id,
            [
                {
                    "group_id": group_id,
                    "group_name": title,
                }
            ],
        )
        if account_id not in self.enabled:
            await self._refresh(account_id)
        if group_id not in self.enabled.get(account_id, set()):
            return
        text, segments, reply = normalize_segments(raw.get("message", event.message_str))
        payload = {
            "platform": "qq",
            "account_id": account_id,
            "external_chat_id": group_id,
            "chat_type": "group",
            "chat_title": title,
            "external_message_id": str(event.message_obj.message_id),
            "sender_id": str(event.get_sender_id()),
            "sender_name": event.get_sender_name() or None,
            "timestamp": int(raw.get("time", time.time())) * 1000,
            "text": text,
            "raw_content": segments,
            "reply_to_message_id": reply,
            "message_type": "text" if all(x.get("type") == "text" for x in segments) else "mixed",
            "is_outgoing": str(event.get_sender_id()) == account_id,
            "metadata": {},
        }
        await asyncio.to_thread(self.outbox.enqueue, payload)

    @filter.on_astrbot_loaded()
    async def discover_groups(self) -> None:
        for platform in self.context.platform_manager.get_insts():
            try:
                client = platform.get_client()
                login = await client.api.call_action("get_login_info")
                groups = await client.api.call_action("get_group_list")
                account_id = str(self._data(login).get("user_id", ""))
                if account_id:
                    await self._upsert_sources(account_id, self._data(groups) or [])
                    await self._refresh(account_id)
            except Exception as exc:
                logger.warning("Chat Insight QQ group discovery failed: %s", type(exc).__name__)

    @staticmethod
    def _data(response: Any) -> Any:
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response

    async def _upsert_sources(self, account_id: str, groups: list[dict[str, Any]]) -> None:
        payload = [
            {
                "platform": "qq",
                "external_account_id": account_id,
                "account_display_name": f"QQ {account_id}",
                "chat_type": "group",
                "external_chat_id": str(group.get("group_id")),
                "title": str(group.get("group_name") or group.get("group_id")),
                "status": "online",
            }
            for group in groups
            if group.get("group_id") is not None
        ]
        if not payload:
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self.core_url}/internal/v1/sources:upsert",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Chat Insight source sync deferred; Core unavailable")

    async def _refresh(self, account_id: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.core_url}/internal/v1/sources/enabled",
                    headers=self.headers,
                    params={"platform": "qq", "account_id": account_id},
                )
                response.raise_for_status()
                self.enabled[account_id] = set(response.json()["external_chat_ids"])
        except httpx.HTTPError:
            pass

    async def _refresh_loop(self) -> None:
        while True:
            for account_id in list(self.enabled):
                await self._refresh(account_id)
            await asyncio.sleep(30)

    async def _sender(self) -> None:
        while True:
            batch = await asyncio.to_thread(self.outbox.peek, 100)
            if not batch:
                await asyncio.sleep(1)
                continue
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(
                        f"{self.core_url}/internal/v1/messages:batch",
                        headers=self.headers,
                        json={"messages": [payload for _, payload in batch]},
                    )
                    response.raise_for_status()
                await asyncio.to_thread(self.outbox.delete, [row_id for row_id, _ in batch])
            except httpx.HTTPError:
                await asyncio.sleep(5)

    async def _heartbeat(self) -> None:
        while True:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        f"{self.core_url}/internal/v1/collectors/heartbeat",
                        headers=self.headers,
                        json={
                            "collector_id": "qq-astrbot-primary",
                            "platform": "qq",
                            "status": "healthy",
                            "detail": {"outbox": await asyncio.to_thread(self.outbox.count)},
                        },
                    )
            except httpx.HTTPError:
                pass
            await asyncio.sleep(30)

    async def terminate(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
