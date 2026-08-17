from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet


def _secret(name: str) -> str | None:
    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    return os.getenv(name)


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    data_dir: Path
    master_key: str
    collector_token: str | None
    setup_token: str | None
    telegram_collector_url: str
    cookie_secure: bool
    environment: str

    @classmethod
    def load(cls) -> Settings:
        environment = os.getenv("CHAT_INSIGHT_ENV", "development")
        master_key = _secret("CHAT_INSIGHT_MASTER_KEY")
        if not master_key:
            if environment == "production":
                raise RuntimeError("CHAT_INSIGHT_MASTER_KEY is required in production")
            master_key = Fernet.generate_key().decode()
        data_dir = Path(os.getenv("CHAT_INSIGHT_DATA_DIR", "./data")).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            database_url=os.getenv(
                "CHAT_INSIGHT_DATABASE_URL",
                f"sqlite+aiosqlite:///{(data_dir / 'chat_insight.db').as_posix()}",
            ),
            data_dir=data_dir,
            master_key=master_key,
            collector_token=_secret("CHAT_INSIGHT_COLLECTOR_TOKEN"),
            setup_token=_secret("CHAT_INSIGHT_SETUP_TOKEN"),
            telegram_collector_url=os.getenv(
                "CHAT_INSIGHT_TELEGRAM_URL", "http://telegram-collector:8090"
            ).rstrip("/"),
            cookie_secure=os.getenv(
                "CHAT_INSIGHT_COOKIE_SECURE", "true" if environment == "production" else "false"
            ).lower()
            == "true",
            environment=environment,
        )
