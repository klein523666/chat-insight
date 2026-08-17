from __future__ import annotations

import time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_ms() -> int:
    return time.time_ns() // 1_000_000


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class WebSession(Base):
    __tablename__ = "web_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("platform", "external_account_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    external_account_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="offline")
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)
    last_seen_at: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("account_id", "external_chat_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(40), default="chat")
    chat_type: Mapped[str] = mapped_column(String(40), index=True)
    external_chat_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), default="")
    username: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    report_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(40), default="online")
    first_seen_at: Mapped[int] = mapped_column(Integer, default=now_ms)
    last_seen_at: Mapped[int] = mapped_column(Integer, default=now_ms)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    account: Mapped[Account] = relationship()


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "account_external_id",
            "external_chat_id",
            "external_message_id",
            name="uq_message_external",
        ),
        Index("uq_message_fallback", "fallback_hash", unique=True),
        Index("ix_messages_window", "source_id", "timestamp"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    account_external_id: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    external_chat_id: Mapped[str] = mapped_column(String(255))
    chat_type: Mapped[str] = mapped_column(String(40))
    chat_title: Mapped[str] = mapped_column(String(500), default="")
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    fallback_hash: Mapped[str | None] = mapped_column(String(64))
    sender_id: Mapped[str | None] = mapped_column(String(255))
    sender_name: Mapped[str | None] = mapped_column(String(500))
    sender_username: Mapped[str | None] = mapped_column(String(255))
    timestamp: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    raw_content: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reply_to_message_id: Mapped[str | None] = mapped_column(String(255))
    message_type: Mapped[str] = mapped_column(String(40), default="text")
    is_outgoing: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class AIProvider(Base):
    __tablename__ = "ai_providers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="OpenAI Compatible")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str] = mapped_column(String(1000), default="")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255), default="")
    max_input_chars: Mapped[int] = mapped_column(Integer, default=60000)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class TelegramCredential(Base):
    __tablename__ = "telegram_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_id: Mapped[int] = mapped_column(Integer)
    api_hash_encrypted: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class DeliveryTarget(Base):
    __tablename__ = "delivery_targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    target_type: Mapped[str] = mapped_column(String(40), default="feishu_webhook")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_encrypted: Mapped[str] = mapped_column(Text)
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class ReportTask(Base):
    __tablename__ = "report_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_type: Mapped[str] = mapped_column(String(20))
    schedule_hour: Mapped[int] = mapped_column(Integer, default=23)
    schedule_minute: Mapped[int] = mapped_column(Integer, default=55)
    timezone: Mapped[str] = mapped_column(String(100), default="Asia/Shanghai")
    window_type: Mapped[str] = mapped_column(String(40))
    prompt_mode: Mapped[str] = mapped_column(String(20), default="adaptive")
    report_prompt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)
    updated_at: Mapped[int] = mapped_column(Integer, default=now_ms)
    sources: Mapped[list[Source]] = relationship(secondary="report_task_sources")
    delivery_targets: Mapped[list[DeliveryTarget]] = relationship(
        secondary="report_task_delivery_targets"
    )


class ReportTaskSource(Base):
    __tablename__ = "report_task_sources"
    task_id: Mapped[int] = mapped_column(
        ForeignKey("report_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )


class ReportTaskDeliveryTarget(Base):
    __tablename__ = "report_task_delivery_targets"
    task_id: Mapped[int] = mapped_column(
        ForeignKey("report_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_targets.id", ondelete="CASCADE"), primary_key=True
    )


class ReportRun(Base):
    __tablename__ = "report_runs"
    __table_args__ = (UniqueConstraint("task_id", "window_start", "window_end"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("report_tasks.id", ondelete="CASCADE"))
    window_start: Mapped[int] = mapped_column(Integer)
    window_end: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="running")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_status: Mapped[str] = mapped_column(String(40), default="not_configured")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[int] = mapped_column(Integer, default=now_ms)
    finished_at: Mapped[int | None] = mapped_column(Integer)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("report_runs.id", ondelete="CASCADE"), unique=True
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("report_tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))
    markdown: Mapped[str] = mapped_column(Text)
    structured_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class DeliveryLog(Base):
    __tablename__ = "delivery_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("delivery_targets.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(40))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    response_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class AppSetting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[int] = mapped_column(Integer, default=now_ms)


class CollectorState(Base):
    __tablename__ = "collector_state"
    collector_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    platform: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="offline")
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[int] = mapped_column(Integer, default=now_ms)
