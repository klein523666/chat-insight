from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class Outbox:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.Lock()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS outbox ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "payload TEXT NOT NULL, created_at INTEGER NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def enqueue(self, payload: dict[str, Any]) -> None:
        with self.lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO outbox(payload, created_at) VALUES (?, ?)",
                (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), int(time.time())),
            )

    def peek(self, limit: int = 100) -> list[tuple[int, dict[str, Any]]]:
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, payload FROM outbox ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        return [(int(row[0]), json.loads(row[1])) for row in rows]

    def delete(self, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self.lock, self._connect() as connection:
            connection.execute(f"DELETE FROM outbox WHERE id IN ({placeholders})", ids)  # noqa: S608

    def count(self) -> int:
        with self.lock, self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
