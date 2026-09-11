"""Pydantic models for stored commands."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CommandRecord(BaseModel):
    id: int | None = None
    user_text: str
    intent: str = ""          # tool_call | conversation
    tool: str = ""
    arguments: dict[str, Any] = {}
    result: str = ""
    status: str = "ok"        # ok | failed | cancelled | expired
    created_at: str = datetime.now().isoformat(timespec="seconds")
