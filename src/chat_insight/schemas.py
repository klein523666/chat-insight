from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SetupRequest(BaseModel):
    setup_token: str = Field(min_length=16, max_length=512)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[\w.@+-]+$")
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class SourceUpsert(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    external_account_id: str = Field(min_length=1, max_length=255)
    account_display_name: str = Field(default="", max_length=255)
    source_type: str = Field(default="chat", max_length=40)
    chat_type: Literal["group", "supergroup", "channel", "private"]
    external_chat_id: str = Field(min_length=1, max_length=255)
    title: str = Field(default="", max_length=500)
    username: str | None = Field(default=None, max_length=255)
    status: str = Field(default="online", max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourcePatch(BaseModel):
    enabled: bool | None = None
    report_enabled: bool | None = None


class SourceBulkPatch(BaseModel):
    source_ids: list[int] = Field(min_length=1, max_length=1000)
    enabled: bool


class UnifiedMessage(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    account_id: str = Field(min_length=1, max_length=255)
    source_id: int | None = None
    external_chat_id: str = Field(min_length=1, max_length=255)
    chat_type: Literal["group", "supergroup", "channel", "private"]
    chat_title: str = Field(default="", max_length=500)
    external_message_id: str | None = Field(default=None, max_length=255)
    sender_id: str | None = Field(default=None, max_length=255)
    sender_name: str | None = Field(default=None, max_length=500)
    sender_username: str | None = Field(default=None, max_length=255)
    timestamp: int = Field(gt=0)
    text: str = Field(default="", max_length=1_000_000)
    raw_content: list[dict[str, Any]] = Field(default_factory=list)
    reply_to_message_id: str | None = Field(default=None, max_length=255)
    message_type: str = Field(default="text", max_length=40)
    is_outgoing: bool = False
    is_bot: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: int) -> int:
        return value * 1000 if value < 10_000_000_000 else value


class MessageBatch(BaseModel):
    messages: list[UnifiedMessage] = Field(min_length=1, max_length=500)


class HeartbeatRequest(BaseModel):
    collector_id: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=40)
    status: str = Field(min_length=1, max_length=40)
    detail: dict[str, Any] = Field(default_factory=dict)


class AIProviderInput(BaseModel):
    enabled: bool = True
    base_url: str = Field(min_length=1, max_length=1000)
    api_key: str | None = Field(default=None, max_length=4096)
    model: str = Field(min_length=1, max_length=255)
    max_input_chars: int = Field(default=60_000, ge=10_000, le=1_000_000)

    @field_validator("base_url")
    @classmethod
    def trim_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must use http or https")
        return value


class DeliveryTargetInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    webhook: HttpUrl
    secret: str | None = Field(default=None, max_length=1024)
    enabled: bool = True


class ReportTaskInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    enabled: bool = True
    source_ids: list[int] = Field(min_length=1)
    schedule_type: Literal["hourly", "daily"]
    schedule_hour: int = Field(default=23, ge=0, le=23)
    schedule_minute: int = Field(default=55, ge=0, le=59)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=100)
    delivery_target_ids: list[int] = Field(default_factory=list)
    report_prompt: str = Field(default="", max_length=4_000)
    prompt_mode: Literal["adaptive", "custom"] = "adaptive"

    @field_validator("report_prompt")
    @classmethod
    def validate_report_prompt(cls, value: str) -> str:
        return value.strip()

    @field_validator("prompt_mode")
    @classmethod
    def validate_prompt_mode(cls, value: str, info: Any) -> str:
        if value == "custom" and not str(info.data.get("report_prompt", "")).strip():
            raise ValueError("自定义提示词不能为空")
        return value


class TelegramConfigInput(BaseModel):
    api_id: int = Field(gt=0)
    api_hash: str = Field(min_length=16, max_length=256)

    @field_validator("api_hash", mode="before")
    @classmethod
    def strip_api_hash(cls, value: str) -> str:
        return value.strip()


class TelegramValueInput(BaseModel):
    value: str = Field(min_length=1, max_length=512)


class AITopic(BaseModel):
    title: str
    summary: str = ""
    evidence_message_ids: list[int] = Field(default_factory=list)


class AIFinding(BaseModel):
    text: str
    evidence_message_ids: list[int] = Field(default_factory=list)


class AIAnalysis(BaseModel):
    summary: str = ""
    topics: list[AITopic] = Field(default_factory=list)
    important_events: list[AIFinding] = Field(default_factory=list)
    user_needs: list[AIFinding] = Field(default_factory=list)
    problems: list[AIFinding] = Field(default_factory=list)
    risks: list[AIFinding] = Field(default_factory=list)
    opportunities: list[AIFinding] = Field(default_factory=list)
    todos: list[AIFinding] = Field(default_factory=list)
    important_quotes: list[AIFinding] = Field(default_factory=list)
    trends: list[AIFinding] = Field(default_factory=list)
    conclusion: str = ""
