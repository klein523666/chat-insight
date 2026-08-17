from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from chat_insight.api import create_app
from chat_insight.config import Settings


def test_core_setup_ingest_and_report(tmp_path, monkeypatch):
    delivered: list[str] = []

    async def fake_delivery(webhook, secret, title, markdown):
        from chat_insight.feishu import DeliveryResult

        delivered.append(title)
        return DeliveryResult(True, 200, None, 1)

    monkeypatch.setattr("chat_insight.reports.send_feishu", fake_delivery)
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        data_dir=tmp_path,
        master_key=Fernet.generate_key().decode(),
        collector_token="collector-test-token-long",
        setup_token="setup-test-token-long-enough",
        telegram_collector_url="http://127.0.0.1:9",
        cookie_secure=False,
        environment="test",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/v1/setup/status").json() == {"required": True}
        created = client.post(
            "/api/v1/setup",
            json={
                "setup_token": settings.setup_token,
                "username": "owner@example.com",
                "password": "correct horse battery staple",
            },
        )
        assert created.status_code == 201
        assert (
            client.post(
                "/api/v1/setup",
                json={
                    "setup_token": settings.setup_token,
                    "username": "other",
                    "password": "another secure password",
                },
            ).status_code
            == 409
        )

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner@example.com", "password": "correct horse battery staple"},
        )
        csrf = login.json()["csrf_token"]
        user_headers = {"X-CSRF-Token": csrf}
        internal_headers = {"Authorization": f"Bearer {settings.collector_token}"}

        source_response = client.post(
            "/internal/v1/sources:upsert",
            headers=internal_headers,
            json=[
                {
                    "platform": "telegram",
                    "external_account_id": "tg-1",
                    "account_display_name": "@owner",
                    "chat_type": "channel",
                    "external_chat_id": "-1001",
                    "title": "AI News",
                }
            ],
        )
        source = source_response.json()["sources"][0]
        assert source["enabled"] is False

        previous_hour_middle = datetime.now(UTC).replace(
            minute=0, second=0, microsecond=0
        ) - timedelta(minutes=30)
        message = {
            "platform": "telegram",
            "account_id": "tg-1",
            "external_chat_id": "-1001",
            "chat_type": "channel",
            "chat_title": "AI News",
            "external_message_id": "99",
            "timestamp": int(previous_hour_middle.timestamp() * 1000),
            "text": "OpenAI API 价格与稳定性讨论",
        }
        rejected = client.post(
            "/internal/v1/messages:batch",
            headers=internal_headers,
            json={"messages": [message]},
        )
        assert rejected.json()["rejected"] == 1
        assert (
            client.patch(
                f"/api/v1/sources/{source['id']}", headers=user_headers, json={"enabled": True}
            ).status_code
            == 200
        )

        accepted = client.post(
            "/internal/v1/messages:batch",
            headers=internal_headers,
            json={"messages": [message]},
        )
        duplicate = client.post(
            "/internal/v1/messages:batch",
            headers=internal_headers,
            json={"messages": [message]},
        )
        assert accepted.json()["accepted"] == 1
        assert duplicate.json()["duplicate"] == 1

        target = client.post(
            "/api/v1/delivery-targets",
            headers=user_headers,
            json={"name": "运营群", "webhook": "https://example.com/webhook"},
        )
        assert target.status_code == 201

        task = client.post(
            "/api/v1/report-tasks",
            headers=user_headers,
            json={
                "name": "AI 小时报",
                "source_ids": [source["id"]],
                "schedule_type": "hourly",
                "schedule_minute": 0,
                "timezone": "UTC",
                "delivery_target_ids": [target.json()["id"]],
            },
        )
        assert task.status_code == 201, task.text
        report = client.post(
            f"/api/v1/report-tasks/{task.json()['id']}/run",
            headers=user_headers,
        )
        assert report.status_code == 200, report.text
        detail = client.get(f"/api/v1/reports/{report.json()['report_id']}")
        assert "openai" in detail.json()["markdown"].lower()
        assert delivered == []
        assert (
            client.post(
                f"/api/v1/report-tasks/{task.json()['id']}/run?deliver=true",
                headers=user_headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/report-tasks/{task.json()['id']}/run?deliver=true",
                headers=user_headers,
            ).status_code
            == 200
        )
        assert len(delivered) == 1

        migrated = client.post(
            "/internal/v1/sources:upsert",
            headers=internal_headers,
            json=[
                {
                    "platform": "telegram",
                    "external_account_id": "tg-1",
                    "chat_type": "channel",
                    "external_chat_id": "-1001",
                    "title": "AI News",
                    "status": "migrated",
                }
            ],
        ).json()["sources"][0]
        assert migrated["enabled"] is False
        assert client.get(
            "/internal/v1/sources/enabled",
            headers=internal_headers,
            params={"platform": "telegram", "account_id": "tg-1"},
        ).json() == {"external_chat_ids": []}
        assert (
            client.patch(
                f"/api/v1/sources/{source['id']}",
                headers=user_headers,
                json={"enabled": True},
            ).status_code
            == 409
        )


def test_csrf_is_required(tmp_path):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'csrf.db').as_posix()}",
        data_dir=tmp_path,
        master_key=Fernet.generate_key().decode(),
        collector_token="collector-test-token-long",
        setup_token="setup-test-token-long-enough",
        telegram_collector_url="http://127.0.0.1:9",
        cookie_secure=False,
        environment="test",
    )
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/setup",
            json={
                "setup_token": settings.setup_token,
                "username": "owner",
                "password": "correct horse battery staple",
            },
        )
        client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "correct horse battery staple"},
        )
        assert client.post("/api/v1/auth/logout").status_code == 403
