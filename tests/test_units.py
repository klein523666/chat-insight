from __future__ import annotations

from datetime import UTC, datetime

from chat_insight.feishu import feishu_signature, split_utf8
from chat_insight.models import Message, ReportTask
from chat_insight.reports import report_window, statistics
from chat_insight.schemas import TelegramConfigInput, UnifiedMessage


def test_timestamp_and_external_ids_remain_strings():
    message = UnifiedMessage(
        platform="qq",
        account_id="00123",
        external_chat_id="0099",
        chat_type="group",
        external_message_id="0007",
        timestamp=1_700_000_000,
    )
    assert message.account_id == "00123"
    assert message.external_message_id == "0007"
    assert message.timestamp == 1_700_000_000_000


def test_hourly_window_is_left_closed_right_open():
    task = ReportTask(schedule_type="hourly", schedule_minute=0, timezone="Asia/Shanghai")
    start, end = report_window(task, datetime(2026, 8, 16, 10, 37, tzinfo=UTC))
    assert end - start == 3_600_000
    assert datetime.fromtimestamp(end / 1000, UTC).minute == 0


def test_channel_is_excluded_from_top_users():
    group = Message(
        platform="qq",
        account_external_id="1",
        source_id=1,
        external_chat_id="1",
        chat_type="group",
        chat_title="群",
        timestamp=1,
        text="API API",
        sender_name="Alice",
    )
    channel = Message(
        platform="telegram",
        account_external_id="2",
        source_id=2,
        external_chat_id="2",
        chat_type="channel",
        chat_title="频道",
        timestamp=2,
        text="API",
        sender_name="Channel",
    )
    assert statistics([group, channel])["top_users"] == [("Alice", 1)]


def test_feishu_helpers_are_deterministic_and_bounded():
    assert feishu_signature(1, "secret") == feishu_signature(1, "secret")
    assert all(len(item.encode()) <= 32 for item in split_utf8("你好世界" * 20, 32))


def test_telegram_api_hash_strips_pasted_whitespace():
    config = TelegramConfigInput(api_id=1, api_hash=" 0123456789abcdef ")
    assert config.api_hash == "0123456789abcdef"
