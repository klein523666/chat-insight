from __future__ import annotations

import json

import httpx
import pytest

from chat_insight.ai import OpenAICompatibleClient, split_messages
from chat_insight.feishu import send_feishu
from chat_insight.models import Message


class FakeClient:
    responses: list[httpx.Response] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        return self.responses.pop(0)


def response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status,
        request=httpx.Request("POST", "https://example.com"),
        json=payload,
    )


@pytest.mark.asyncio
async def test_ai_falls_back_when_json_schema_is_rejected(monkeypatch):
    valid = {
        "summary": "正常",
        "topics": [],
        "important_events": [],
        "user_needs": [],
        "problems": [],
        "risks": [],
        "opportunities": [],
        "todos": [],
        "important_quotes": [],
        "trends": [],
        "conclusion": "完成",
    }
    FakeClient.responses = [
        response(400, {"error": "unsupported response format"}),
        response(200, {"choices": [{"message": {"content": json.dumps(valid)}}]}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await OpenAICompatibleClient("https://example.com/v1", "key", "model").test()
    assert result.summary == "正常"
    assert FakeClient.responses == []


@pytest.mark.asyncio
async def test_feishu_retries_429(monkeypatch):
    FakeClient.responses = [
        response(429, {"code": 99991400}),
        response(200, {"code": 0}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    async def no_sleep(_):
        return None

    monkeypatch.setattr("chat_insight.feishu.asyncio.sleep", no_sleep)
    result = await send_feishu("https://example.com/hook", "secret", "报告", "内容")
    assert result.success is True
    assert result.attempts == 2


def test_one_hundred_thousand_messages_are_chunked():
    message = Message(
        id=1,
        platform="telegram",
        account_external_id="1",
        source_id=1,
        external_chat_id="1",
        chat_type="group",
        chat_title="群",
        timestamp=1,
        text="A moderately sized message for the context budget.",
    )
    chunks = split_messages((message for _ in range(100_000)), 30_000)
    assert len(chunks) > 100
    assert sum(map(len, chunks)) == 100_000
