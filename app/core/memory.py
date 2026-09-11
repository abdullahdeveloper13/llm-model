"""Conversation memory: short rolling history for the LLM, backed by SQLite."""
from __future__ import annotations

from app.storage.database import Database
from app.utils.logger import get_logger

log = get_logger(__name__)

MAX_CONTEXT = 10


class Memory:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._recent_turns: list[dict[str, str]] = []

    def remember_turn(self, user_text: str, assistant_text: str) -> None:
        self._recent_turns.append({"role": "user", "content": user_text})
        self._recent_turns.append({"role": "assistant", "content": assistant_text})
        self._recent_turns = self._recent_turns[-MAX_CONTEXT * 2:]

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._recent_turns)

    def log_command(self, user_text: str, intent: str, tool: str = "",
                    arguments: dict | None = None, result: str = "", status: str = "ok") -> int:
        return self.db.log_command(user_text, intent, tool, arguments, result, status)
