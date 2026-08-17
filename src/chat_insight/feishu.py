from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

import httpx


def feishu_signature(timestamp: int, secret: str) -> str:
    key = f"{timestamp}\n{secret}".encode()
    return base64.b64encode(hmac.new(key, digestmod=hashlib.sha256).digest()).decode()


def split_utf8(text: str, max_bytes: int = 24_000) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        encoded = len(line.encode())
        if current and size + encoded > max_bytes:
            parts.append("".join(current))
            current, size = [], 0
        if encoded > max_bytes:
            for char in line:
                char_size = len(char.encode())
                if current and size + char_size > max_bytes:
                    parts.append("".join(current))
                    current, size = [], 0
                current.append(char)
                size += char_size
        else:
            current.append(line)
            size += encoded
    if current:
        parts.append("".join(current))
    return parts or [""]


@dataclass(slots=True)
class DeliveryResult:
    success: bool
    status_code: int | None
    error: str | None
    attempts: int


async def send_feishu(
    webhook: str, secret: str | None, title: str, markdown: str
) -> DeliveryResult:
    attempts = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for index, chunk in enumerate(split_utf8(markdown), start=1):
            subtitle = title if index == 1 else f"{title}（续 {index}）"
            payload: dict[str, object] = {
                "msg_type": "interactive",
                "card": {
                    "config": {"wide_screen_mode": True},
                    "header": {"title": {"tag": "plain_text", "content": subtitle}},
                    "elements": [{"tag": "markdown", "content": chunk}],
                },
            }
            if secret:
                timestamp = int(time.time())
                payload.update(
                    {"timestamp": str(timestamp), "sign": feishu_signature(timestamp, secret)}
                )
            for attempt in range(1, 4):
                attempts += 1
                try:
                    response = await client.post(webhook, json=payload)
                    body = response.json() if response.content else {}
                    if response.is_success and body.get("code", body.get("StatusCode", 0)) == 0:
                        break
                    if response.status_code != 429 and response.status_code < 500:
                        return DeliveryResult(
                            False, response.status_code, "Feishu rejected message", attempts
                        )
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == 3:
                        return DeliveryResult(False, None, type(exc).__name__, attempts)
                if attempt == 3:
                    return DeliveryResult(False, response.status_code, "retry exhausted", attempts)
                await asyncio.sleep(2 ** (attempt - 1))
    return DeliveryResult(True, 200, None, attempts)
