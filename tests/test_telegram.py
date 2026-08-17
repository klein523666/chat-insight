from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from chat_insight.telegram.service import (
    CollectorSettings,
    TelegramAuthenticationError,
    TelegramCollector,
    TelegramNotConfiguredError,
    classify_chat,
    normalize_content,
    safe_authentication_error,
    telegram_folder_names,
    telegram_folder_title,
    upgraded_basic_group_id,
)


class FakeTD:
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = responses or []
        self.requests: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(payload)
        return self.responses.pop(0) if self.responses else {"@type": "ok"}

    def start(self, handler: Any) -> None:
        self.handler = handler


def collector(tmp_path: Path, backfill_hours: int = 3) -> TelegramCollector:
    return TelegramCollector(
        CollectorSettings(
            core_url="http://core",
            collector_token="token",
            tdlib_library="tdjson",
            data_dir=tmp_path,
            database_key="database-key",
            backfill_hours=backfill_hours,
        )
    )


def test_telegram_content_normalization():
    text, kind, raw = normalize_content({"@type": "messagePhoto", "caption": {"text": "架构图"}})
    assert text == "[图片] 架构图"
    assert kind == "image"
    assert raw == [{"type": "image", "caption": "架构图"}]


def test_telegram_channel_classification():
    chat = {"type": {"@type": "chatTypeSupergroup", "supergroup_id": 88}}
    assert classify_chat(chat, {"88": {"is_channel": True}}) == "channel"
    assert classify_chat(chat, {"88": {"is_channel": False}}) == "supergroup"
    assert classify_chat({"type": {"@type": "chatTypePrivate"}}, {}) is None


def test_upgraded_basic_group_is_identified():
    chat = {"type": {"@type": "chatTypeBasicGroup", "basic_group_id": 7}}

    assert upgraded_basic_group_id(chat, {"7": {"upgraded_to_supergroup_id": 88}}) == "88"
    assert upgraded_basic_group_id(chat, {"7": {"upgraded_to_supergroup_id": 0}}) is None


def test_telegram_folder_names_read_folder_positions():
    chat = {
        "positions": [
            {"list": {"@type": "chatListFolder", "chat_folder_id": 2}, "order": 1},
            {"list": {"@type": "chatListFolder", "chat_folder_id": 3}, "order": 0},
        ]
    }
    assert telegram_folder_names(chat, {"2": "工作", "3": "静音"}) == ["工作"]


def test_telegram_folder_title_unwraps_formatted_text():
    folder = {"name": {"text": {"@type": "formattedText", "text": "卡网"}}}
    assert telegram_folder_title(folder) == "卡网"


@pytest.mark.asyncio
async def test_wait_tdlib_parameters_keeps_database_key_encoded(tmp_path):
    instance = collector(tmp_path)
    td = FakeTD()
    instance.td = td  # type: ignore[assignment]
    instance.api_id = 123
    instance.api_hash = "api-hash"

    await instance._authorization({"@type": "authorizationStateWaitTdlibParameters"})

    assert td.sent[0]["@type"] == "setTdlibParameters"
    assert base64.b64decode(td.sent[0]["database_encryption_key"]).decode() == "database-key"
    assert instance.state.authorization_state == "WaitTdlibParameters"


@pytest.mark.asyncio
async def test_configure_reads_initial_authorization_state(tmp_path, monkeypatch):
    td = FakeTD([{"@type": "authorizationStateWaitTdlibParameters"}])
    monkeypatch.setattr("chat_insight.telegram.service.TDJson", lambda _: td)
    instance = collector(tmp_path)

    await instance.configure(123, "api-hash")

    assert td.requests == [{"@type": "getAuthorizationState"}]
    assert td.sent[0]["@type"] == "setTdlibParameters"
    assert instance.state.authorization_state == "WaitTdlibParameters"


@pytest.mark.parametrize(
    ("action", "request_type"),
    [
        ("qr", "requestQrCodeAuthentication"),
        ("phone", "setAuthenticationPhoneNumber"),
        ("code", "checkAuthenticationCode"),
        ("password", "checkAuthenticationPassword"),
        ("email", "setAuthenticationEmailAddress"),
        ("email-code", "checkAuthenticationEmailCode"),
        ("logout", "logOut"),
    ],
)
@pytest.mark.asyncio
async def test_auth_actions_are_forwarded(tmp_path, action, request_type):
    instance = collector(tmp_path)
    td = FakeTD()
    instance.td = td  # type: ignore[assignment]

    await instance.auth(action, "sensitive-value")

    assert td.requests[0]["@type"] == request_type


@pytest.mark.asyncio
async def test_auth_requires_configuration(tmp_path):
    with pytest.raises(TelegramNotConfiguredError):
        await collector(tmp_path).auth("qr")


@pytest.mark.asyncio
async def test_failed_qr_request_clears_previous_link(tmp_path):
    instance = collector(tmp_path)
    instance.td = FakeTD([{"@type": "error", "message": "AUTH_TOKEN_INVALID"}])  # type: ignore[assignment]
    instance.state.qr_link = "tg://login?token=previous"

    with pytest.raises(TelegramAuthenticationError, match="AUTH_TOKEN_INVALID"):
        await instance.auth("qr")

    assert instance.state.qr_link is None


def test_authentication_error_code_excludes_unstructured_details():
    assert safe_authentication_error("AUTH_TOKEN_INVALID") == "AUTH_TOKEN_INVALID"
    assert safe_authentication_error("number +86138 is invalid") == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_late_supergroup_update_resyncs_channel_classification(tmp_path, monkeypatch):
    instance = collector(tmp_path)
    chat = {
        "id": -1001,
        "title": "公告频道",
        "type": {"@type": "chatTypeSupergroup", "supergroup_id": 88},
    }
    instance.chats["-1001"] = chat
    instance.state.account_id = "42"
    sync = AsyncMock()
    monkeypatch.setattr(instance, "_sync_chat", sync)

    await instance._update(
        {"@type": "updateSupergroup", "supergroup": {"id": 88, "is_channel": True}}
    )

    sync.assert_awaited_once_with(chat)
    assert classify_chat(chat, instance.supergroups) == "channel"


@pytest.mark.asyncio
async def test_upgraded_basic_group_loads_missing_legacy_chat(tmp_path, monkeypatch):
    chat = {
        "@type": "chat",
        "id": -7,
        "title": "旧群",
        "type": {"@type": "chatTypeBasicGroup", "basic_group_id": 7},
    }
    instance = collector(tmp_path)
    td = FakeTD([chat])
    instance.td = td  # type: ignore[assignment]
    sync = AsyncMock()
    monkeypatch.setattr(instance, "_sync_chat", sync)

    await instance._update(
        {
            "@type": "updateBasicGroup",
            "basic_group": {"id": 7, "upgraded_to_supergroup_id": 88},
        }
    )

    assert td.requests == [
        {
            "@type": "createBasicGroupChat",
            "basic_group_id": 7,
            "force": True,
        }
    ]
    assert instance.chats["-7"] == chat
    sync.assert_awaited_once_with(chat)


@pytest.mark.asyncio
async def test_folder_lists_are_loaded_once(tmp_path):
    instance = collector(tmp_path)
    td = FakeTD([{"@type": "error", "code": 404}])
    instance.td = td  # type: ignore[assignment]
    instance.folders = {"2": "工作"}

    await instance._load_folder_chats()

    assert td.requests == [
        {
            "@type": "loadChats",
            "chat_list": {"@type": "chatListFolder", "chat_folder_id": 2},
            "limit": 100,
        }
    ]
    assert instance.loaded_folder_ids == {"2"}


@pytest.mark.asyncio
async def test_backfill_stops_before_processing_repeated_page(tmp_path, monkeypatch):
    now = int(time.time())
    page = {
        "@type": "messages",
        "messages": [
            {"id": 99, "chat_id": -1001, "date": now, "content": {"@type": "messageText"}}
        ],
    }
    td = FakeTD([page.copy(), page.copy()])
    instance = collector(tmp_path)
    instance.td = td  # type: ignore[assignment]
    instance.enabled = {"-1001"}
    accept = AsyncMock()
    monkeypatch.setattr(instance, "_new_message", accept)

    await instance._backfill()

    assert len(td.requests) == 2
    accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_message_diagnostics_distinguish_disabled_and_queued(tmp_path):
    instance = collector(tmp_path)
    instance.state.account_id = "42"
    instance.chats["-1001"] = {
        "id": -1001,
        "title": "测试群",
        "type": {"@type": "chatTypeBasicGroup", "basic_group_id": 1},
    }
    instance.synced_sources.add("-1001")
    message = {
        "id": 99,
        "chat_id": -1001,
        "date": int(time.time()),
        "is_outgoing": True,
        "content": {"@type": "messageText", "text": {"text": "验收标记"}},
    }

    await instance._update({"@type": "updateNewMessage", "message": message})
    instance.enabled.add("-1001")
    await instance._update({"@type": "updateNewMessage", "message": message})

    assert instance.state.new_message_updates == 2
    assert instance.state.messages_dropped_disabled == 1
    assert instance.state.messages_queued == 1
    assert (await instance.outgoing.get())["is_outgoing"] is True
