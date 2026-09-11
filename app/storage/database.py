"""SQLite command history (stdlib sqlite3, thread-safe via a lock)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from app.config.settings import settings
from app.storage.models import CommandRecord
from app.utils.logger import get_logger

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_text TEXT NOT NULL,
    intent TEXT,
    tool TEXT,
    arguments TEXT,
    result TEXT,
    status TEXT,
    created_at TEXT
);
"""


class Database:
    def __init__(self, path: str | None = None) -> None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path or str(settings.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
        log.info("Database ready at %s", path or settings.db_path)

    def log_command(
        self,
        user_text: str,
        intent: str,
        tool: str = "",
        arguments: dict | None = None,
        result: str = "",
        status: str = "ok",
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO commands (user_text, intent, tool, arguments, result, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user_text,
                    intent,
                    tool,
                    json.dumps(arguments or {}),
                    result[:2000],
                    status,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def recent(self, limit: int = 50) -> list[CommandRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            CommandRecord(
                id=r["id"],
                user_text=r["user_text"],
                intent=r["intent"] or "",
                tool=r["tool"] or "",
                arguments=json.loads(r["arguments"] or "{}"),
                result=r["result"] or "",
                status=r["status"] or "",
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
