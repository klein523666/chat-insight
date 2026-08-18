from __future__ import annotations

import asyncio
import base64
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .tdjson import TDJson

MEDIA = {
    "messagePhoto": ("[图片]", "image"),
    "messageVideo": ("[视频]", "video"),
    "messageDocument": ("[文件]", "file"),
    "messageAudio": ("[音频]", "audio"),
    "messageVoiceNote": ("[语音]", "voice"),
    "messageAnimation": ("[GIF]", "animation"),
    "messageSticker": ("[贴纸]", "sticker"),
}


class TelegramNotConfiguredError(RuntimeError):
    """Raised when an authentication action is requested before TDLib starts."""


class TelegramAuthenticationError(RuntimeError):
    """An authentication failure with a safe, Telegram-provided error code."""


def safe_authentication_error(value: object) -> str:
    candidate = str(value).upper()
    return candidate if re.fullmatch(r"[A-Z0-9_]{1,80}", candidate) else "AUTHENTICATION_FAILED"


def normalize_content(content: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    kind = str(content.get("@type", "unknown"))
    if kind == "messageText":
        text = str(content.get("text", {}).get("text", ""))
        return text, "text", [{"type": "text", "text": text}]
    placeholder, message_type = MEDIA.get(kind, (f"[{kind}]", "other"))
    caption = content.get("caption", {}).get("text", "")
    text = f"{placeholder} {caption}".strip()
    return text, message_type, [{"type": message_type, "caption": caption}]


def classify_chat(chat: dict[str, Any], supergroups: dict[str, dict[str, Any]]) -> str | None:
    chat_type = chat.get("type", {})
    kind = chat_type.get("@type")
    if kind == "chatTypeBasicGroup":
        return "group"
    if kind == "chatTypeSupergroup":
        group = supergroups.get(str(chat_type.get("supergroup_id")), {})
        return "channel" if group.get("is_channel") else "supergroup"
    return None


def upgraded_basic_group_id(
    chat: dict[str, Any], basic_groups: dict[str, dict[str, Any]]
) -> str | None:
    chat_type = chat.get("type", {})
    if chat_type.get("@type") != "chatTypeBasicGroup":
        return None
    group = basic_groups.get(str(chat_type.get("basic_group_id")), {})
    upgraded_to = group.get("upgraded_to_supergroup_id")
    return str(upgraded_to) if upgraded_to else None


def telegram_folder_names(chat: dict[str, Any], folders: dict[str, str]) -> list[str]:
    lists = [
        position.get("list", {})
        for position in chat.get("positions", [])
        if position.get("order", 0)
    ] + chat.get("chat_lists", [])
    folder_ids = {
        str(item.get("chat_folder_id"))
        for item in lists
        if item.get("@type") == "chatListFolder" and item.get("chat_folder_id") is not None
    }
    return [folders[folder_id] for folder_id in sorted(folder_ids) if folder_id in folders]


def telegram_folder_title(folder: dict[str, Any]) -> str:
    value: object = folder.get("name", {}).get("text", "")
    while isinstance(value, dict):
        value = value.get("text", "")
    return str(value)


@dataclass(frozen=True, slots=True)
class CollectorSettings:
    core_url: str
    collector_token: str
    tdlib_library: str
    data_dir: Path
    database_key: str
    backfill_hours: int = 3

    @classmethod
    def load(cls) -> CollectorSettings:
        token_file = os.getenv("CHAT_INSIGHT_COLLECTOR_TOKEN_FILE")
        key_file = os.getenv("TDLIB_DATABASE_KEY_FILE")
        collector_token = (
            Path(token_file).read_text(encoding="utf-8").strip()
            if token_file
            else os.getenv("CHAT_INSIGHT_COLLECTOR_TOKEN", "")
        )
        database_key = (
            Path(key_file).read_text(encoding="utf-8").strip()
            if key_file
            else os.getenv("TDLIB_DATABASE_KEY", "")
        )
        if not collector_token or not database_key:
            raise RuntimeError("Collector token and TDLib database key are required")
        data = Path(os.getenv("TDLIB_DATA_DIR", "/data/telegram"))
        data.mkdir(parents=True, exist_ok=True)
        return cls(
            core_url=os.getenv("CHAT_INSIGHT_CORE_URL", "http://chat-insight:8080").rstrip("/"),
            collector_token=collector_token,
            tdlib_library=os.getenv("TDLIB_LIBRARY", "/usr/local/lib/libtdjson.so"),
            data_dir=data,
            database_key=database_key,
            backfill_hours=int(os.getenv("TELEGRAM_BACKFILL_HOURS", "3")),
        )


@dataclass(slots=True)
class TelegramState:
    authorization_state: str = "not_configured"
    qr_link: str | None = None
    account_id: str | None = None
    username: str | None = None
    display_name: str | None = None
    chat_count: int = 0
    last_error: str | None = None
    new_message_updates: int = 0
    messages_dropped_unknown_chat: int = 0
    messages_dropped_disabled: int = 0
    messages_queued: int = 0
    backfill_requests: int = 0
    backfill_messages: int = 0
    backfill_errors: int = 0


class TelegramCollector:
    def __init__(self, settings: CollectorSettings) -> None:
        self.settings = settings
        self.state = TelegramState()
        self.td: TDJson | None = None
        self.api_id: int | None = None
        self.api_hash: str | None = None
        self.chats: dict[str, dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {}
        self.basic_groups: dict[str, dict[str, Any]] = {}
        self.supergroups: dict[str, dict[str, Any]] = {}
        self.folders: dict[str, str] = {}
        self.loaded_folder_ids: set[str] = set()
        self.enabled: set[str] = set()
        self.synced_sources: set[str] = set()
        self.outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=5000)
        self.tasks: list[asyncio.Task[None]] = []

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.collector_token}"}

    async def start(self) -> None:
        self.tasks = [
            asyncio.create_task(self._sender(), name="telegram-core-sender"),
            asyncio.create_task(self._poll_enabled(), name="telegram-enabled-poll"),
            asyncio.create_task(self._heartbeat(), name="telegram-heartbeat"),
        ]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.settings.core_url}/internal/v1/telegram/config", headers=self.headers
                )
                if response.is_success:
                    await self.configure(**response.json())
        except httpx.HTTPError:
            self.state.last_error = "core_unavailable"

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.td:
            await self.td.close()

    async def configure(self, api_id: int, api_hash: str) -> None:
        if self.td and self.api_id == api_id and self.api_hash == api_hash:
            return
        if self.td and self.state.authorization_state == "Ready":
            raise RuntimeError(
                "Log out of the current Telegram account before changing API credentials"
            )
        if self.td:
            await self.td.close()
            self.td = None
        self.api_id, self.api_hash = api_id, api_hash
        try:
            self.td = TDJson(self.settings.tdlib_library)
            self.td.start(self._update)
            self.state.authorization_state = "starting"
            authorization = await self.td.request({"@type": "getAuthorizationState"})
            if authorization.get("@type") != "error":
                await self._authorization(authorization)
        except Exception as exc:
            self.state.authorization_state = "library_error"
            self.state.last_error = str(exc)
            raise

    async def auth(self, action: str, value: str | None = None) -> None:
        if not self.td:
            raise TelegramNotConfiguredError("Telegram is not configured")
        requests: dict[str, dict[str, Any]] = {
            "qr": {"@type": "requestQrCodeAuthentication", "other_user_ids": []},
            "phone": {"@type": "setAuthenticationPhoneNumber", "phone_number": value},
            "code": {"@type": "checkAuthenticationCode", "code": value},
            "password": {"@type": "checkAuthenticationPassword", "password": value},
            "email": {"@type": "setAuthenticationEmailAddress", "email_address": value},
            "email-code": {
                "@type": "checkAuthenticationEmailCode",
                "code": {"@type": "emailAddressAuthenticationCode", "code": value},
            },
            "logout": {"@type": "logOut"},
        }
        response = await self.td.request(requests[action])
        if response.get("@type") == "error":
            error = safe_authentication_error(response.get("message"))
            self.state.last_error = error
            if action == "qr":
                self.state.qr_link = None
            raise TelegramAuthenticationError(error)

    async def _update(self, update: dict[str, Any]) -> None:
        kind = update.get("@type")
        if kind == "updateAuthorizationState":
            await self._authorization(update["authorization_state"])
        elif kind == "updateNewChat":
            chat = update["chat"]
            self.chats[str(chat["id"])] = chat
            await self._sync_chat(chat)
        elif kind == "updateChatTitle":
            chat = self.chats.get(str(update["chat_id"]))
            if chat:
                chat["title"] = update["title"]
                await self._sync_chat(chat)
        elif kind == "updateUser":
            self.users[str(update["user"]["id"])] = update["user"]
        elif kind == "updateBasicGroup":
            group = update["basic_group"]
            self.basic_groups[str(group["id"])] = group
            matched = False
            for chat in self.chats.values():
                chat_type = chat.get("type", {})
                if chat_type.get("@type") == "chatTypeBasicGroup" and str(
                    chat_type.get("basic_group_id")
                ) == str(group["id"]):
                    matched = True
                    await self._sync_chat(chat)
            if not matched and group.get("upgraded_to_supergroup_id") and self.td:
                chat = await self.td.request(
                    {
                        "@type": "createBasicGroupChat",
                        "basic_group_id": group["id"],
                        "force": True,
                    }
                )
                if chat.get("@type") == "chat":
                    self.chats[str(chat["id"])] = chat
                    await self._sync_chat(chat)
        elif kind == "updateSupergroup":
            group = update["supergroup"]
            self.supergroups[str(group["id"])] = group
            for chat in self.chats.values():
                chat_type = chat.get("type", {})
                if chat_type.get("@type") == "chatTypeSupergroup" and str(
                    chat_type.get("supergroup_id")
                ) == str(group["id"]):
                    await self._sync_chat(chat)
        elif kind == "updateChatFolders":
            self.folders = {
                str(folder["id"]): telegram_folder_title(folder)
                for folder in update.get("chat_folders", [])
                if telegram_folder_title(folder)
            }
            for chat in self.chats.values():
                await self._sync_chat(chat)
            if self.state.account_id:
                await self._load_folder_chats()
        elif kind == "updateChatPosition":
            chat = self.chats.get(str(update["chat_id"]))
            if chat:
                self._update_chat_position(chat, update["position"])
                await self._sync_chat(chat)
        elif kind == "updateNewMessage":
            self.state.new_message_updates += 1
            await self._new_message(update["message"])

    def _update_chat_position(self, chat: dict[str, Any], position: dict[str, Any]) -> None:
        target = position.get("list", {})
        positions = chat.setdefault("positions", [])
        matches = [item for item in positions if item.get("list") == target]
        chat["positions"] = [item for item in positions if item not in matches]
        if position.get("order", 0):
            chat["positions"].append(position)

    async def _authorization(self, state: dict[str, Any]) -> None:
        kind = str(state.get("@type", "unknown"))
        self.state.authorization_state = kind.removeprefix("authorizationState")
        self.state.qr_link = state.get("link")
        if kind == "authorizationStateWaitTdlibParameters":
            assert self.td and self.api_id and self.api_hash
            key = base64.b64encode(self.settings.database_key.encode()).decode()
            self.td.send(
                {
                    "@type": "setTdlibParameters",
                    "use_test_dc": False,
                    "database_directory": str(self.settings.data_dir / "database"),
                    "files_directory": str(self.settings.data_dir / "files"),
                    "database_encryption_key": key,
                    "use_file_database": True,
                    "use_chat_info_database": True,
                    "use_message_database": True,
                    "use_secret_chats": False,
                    "api_id": self.api_id,
                    "api_hash": self.api_hash,
                    "system_language_code": "zh-CN",
                    "device_model": "Chat Insight",
                    "system_version": "Linux",
                    "application_version": "0.1.2",
                }
            )
        elif kind == "authorizationStateReady":
            assert self.td
            me = await self.td.request({"@type": "getMe"})
            self.state.account_id = str(me["id"])
            self.state.username = next(
                (item for item in me.get("usernames", {}).get("active_usernames", [])), None
            )
            self.state.display_name = " ".join(
                part for part in [me.get("first_name"), me.get("last_name")] if part
            )
            for chat in self.chats.values():
                await self._sync_chat(chat)
            asyncio.create_task(self._load_chats())

    async def _load_chats(self) -> None:
        assert self.td
        await self._load_chat_list(None)
        await self._load_folder_chats()
        self.state.chat_count = len(self.chats)
        await self._refresh_enabled()
        if self.settings.backfill_hours > 0:
            await self._backfill()

    async def _load_folder_chats(self) -> None:
        for folder_id in sorted(set(self.folders) - self.loaded_folder_ids, key=int):
            loaded = await self._load_chat_list(
                {"@type": "chatListFolder", "chat_folder_id": int(folder_id)}
            )
            if loaded:
                self.loaded_folder_ids.add(folder_id)
        self.state.chat_count = len(self.chats)

    async def _load_chat_list(self, chat_list: dict[str, Any] | None) -> bool:
        assert self.td
        while True:
            response = await self.td.request(
                {"@type": "loadChats", "chat_list": chat_list, "limit": 100}
            )
            if response.get("@type") == "error" and response.get("code") == 404:
                return True
            if response.get("@type") == "error":
                self.state.last_error = str(response.get("message"))
                return False

    async def _sync_chat(self, chat: dict[str, Any]) -> None:
        chat_type = classify_chat(chat, self.supergroups)
        if not chat_type or not self.state.account_id:
            return
        upgraded_to = upgraded_basic_group_id(chat, self.basic_groups)
        metadata: dict[str, Any] = {
            "telegram_folders": telegram_folder_names(chat, self.folders)
        }
        if upgraded_to:
            metadata["upgraded_to_supergroup_id"] = upgraded_to
        payload = [
            {
                "platform": "telegram",
                "external_account_id": self.state.account_id,
                "account_display_name": self.state.username
                or self.state.display_name
                or "Telegram",
                "chat_type": chat_type,
                "external_chat_id": str(chat["id"]),
                "title": chat.get("title", ""),
                "status": "migrated" if upgraded_to else "online",
                "metadata": metadata,
            }
        ]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.settings.core_url}/internal/v1/sources:upsert",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                self.synced_sources.add(str(chat["id"]))
        except httpx.HTTPError:
            self.state.last_error = "source_sync_failed"

    async def _new_message(self, message: dict[str, Any]) -> None:
        chat_id = str(message["chat_id"])
        chat = self.chats.get(chat_id)
        if not chat:
            self.state.messages_dropped_unknown_chat += 1
            return
        if upgraded_basic_group_id(chat, self.basic_groups):
            self.state.messages_dropped_disabled += 1
            return
        if chat_id not in self.synced_sources:
            await self._sync_chat(chat)
        if chat_id not in self.enabled:
            self.state.messages_dropped_disabled += 1
            return
        normalized = self._normalize_message(message, chat)
        if normalized:
            await self.outgoing.put(normalized)
            self.state.messages_queued += 1

    def _normalize_message(
        self, message: dict[str, Any], chat: dict[str, Any]
    ) -> dict[str, Any] | None:
        chat_type = classify_chat(chat, self.supergroups)
        if not chat_type or not self.state.account_id:
            return None
        sender = message.get("sender_id", {})
        sender_id: str | None = None
        sender_name: str | None = None
        sender_username: str | None = None
        is_bot = False
        if sender.get("@type") == "messageSenderUser":
            sender_id = str(sender.get("user_id"))
            user = self.users.get(sender_id, {})
            sender_name = (
                " ".join(part for part in [user.get("first_name"), user.get("last_name")] if part)
                or None
            )
            sender_username = next(
                (item for item in user.get("usernames", {}).get("active_usernames", [])), None
            )
            is_bot = user.get("type", {}).get("@type") == "userTypeBot"
        elif sender.get("@type") == "messageSenderChat":
            sender_id = str(sender.get("chat_id"))
            sender_name = self.chats.get(sender_id, {}).get("title")
        text, message_type, raw = normalize_content(message.get("content", {}))
        reply = message.get("reply_to", {})
        return {
            "platform": "telegram",
            "account_id": self.state.account_id,
            "external_chat_id": str(message["chat_id"]),
            "chat_type": chat_type,
            "chat_title": chat.get("title", ""),
            "external_message_id": str(message["id"]),
            "sender_id": sender_id,
            "sender_name": sender_name,
            "sender_username": sender_username,
            "timestamp": int(message["date"]) * 1000,
            "text": text,
            "raw_content": raw,
            "reply_to_message_id": (
                str(reply.get("message_id"))
                if reply.get("@type") == "messageReplyToMessage"
                else None
            ),
            "message_type": message_type,
            "is_outgoing": bool(message.get("is_outgoing")),
            "is_bot": is_bot,
            "metadata": {"is_channel_post": bool(message.get("is_channel_post"))},
        }

    async def _sender(self) -> None:
        while True:
            first = await self.outgoing.get()
            batch = [first]
            while len(batch) < 100 and not self.outgoing.empty():
                batch.append(self.outgoing.get_nowait())
            while True:
                try:
                    async with httpx.AsyncClient(timeout=20) as client:
                        response = await client.post(
                            f"{self.settings.core_url}/internal/v1/messages:batch",
                            headers=self.headers,
                            json={"messages": batch},
                        )
                        response.raise_for_status()
                    break
                except httpx.HTTPError:
                    self.state.last_error = "message_delivery_failed"
                    await asyncio.sleep(5)
            for _ in batch:
                self.outgoing.task_done()

    async def _refresh_enabled(self) -> None:
        if not self.state.account_id:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.settings.core_url}/internal/v1/sources/enabled",
                    headers=self.headers,
                    params={"platform": "telegram", "account_id": self.state.account_id},
                )
                response.raise_for_status()
                self.enabled = set(response.json()["external_chat_ids"])
        except httpx.HTTPError:
            self.state.last_error = "enabled_source_sync_failed"

    async def _poll_enabled(self) -> None:
        while True:
            await self._refresh_enabled()
            await asyncio.sleep(10)

    async def _backfill(self) -> None:
        if not self.td:
            return
        cutoff = int(time.time()) - self.settings.backfill_hours * 3600
        for chat_id in list(self.enabled):
            from_message_id = 0
            while True:
                response = await self.td.request(
                    {
                        "@type": "getChatHistory",
                        "chat_id": int(chat_id),
                        "from_message_id": from_message_id,
                        "offset": 0,
                        "limit": 100,
                        "only_local": False,
                    }
                )
                self.state.backfill_requests += 1
                if response.get("@type") == "error":
                    self.state.backfill_errors += 1
                    self.state.last_error = "history_backfill_failed"
                    break
                messages = response.get("messages", [])
                self.state.backfill_messages += len(messages)
                if not messages:
                    break
                next_message_id = int(messages[-1]["id"])
                if next_message_id == from_message_id:
                    break
                for message in reversed(messages):
                    if int(message.get("date", 0)) >= cutoff:
                        await self._new_message(message)
                oldest = messages[-1]
                if int(oldest.get("date", 0)) < cutoff:
                    break
                from_message_id = next_message_id

    async def _heartbeat(self) -> None:
        while True:
            payload = {
                "collector_id": "telegram-primary",
                "platform": "telegram",
                "status": "healthy" if self.state.authorization_state == "Ready" else "warning",
                "detail": {
                    "authorization_state": self.state.authorization_state,
                    "chat_count": self.state.chat_count,
                },
            }
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        f"{self.settings.core_url}/internal/v1/collectors/heartbeat",
                        headers=self.headers,
                        json=payload,
                    )
            except httpx.HTTPError:
                pass
            await asyncio.sleep(30)
