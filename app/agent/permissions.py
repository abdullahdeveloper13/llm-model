"""Permission layer: categorises tool requests and enforces confirmation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)

SAFE = "safe"
CONFIRMATION = "confirmation"
BLOCKED = "blocked"

# Tools that must NEVER be reachable, no matter what the LLM says.
BLOCKED_TOOLS = {
    "run_shell",
    "run_powershell",
    "execute_python",
    "read_credentials",
    "disable_firewall",
    "disable_antivirus",
}


@dataclass
class PendingAction:
    tool: str
    arguments: dict
    requested_text: str
    expires_at: datetime

    def expired(self) -> bool:
        return datetime.now() > self.expires_at


class PermissionDecision:
    def __init__(self, allowed: bool, reason: str, needs_confirmation: bool = False) -> None:
        self.allowed = allowed
        self.reason = reason
        self.needs_confirmation = needs_confirmation


class PermissionManager:
    """Checks a tool call against the permission model."""

    def __init__(self) -> None:
        self.pending: PendingAction | None = None

    def check(self, tool) -> PermissionDecision:
        if tool.name in BLOCKED_TOOLS or tool.category == BLOCKED:
            log.warning("Blocked tool requested: %s", tool.name)
            return PermissionDecision(False, "This operation is blocked for security reasons.")
        if tool.category == CONFIRMATION:
            return PermissionDecision(True, "Requires user confirmation.", needs_confirmation=True)
        return PermissionDecision(True, "Safe operation.")

    def stage(self, tool_name: str, arguments: dict, requested_text: str) -> PendingAction:
        self.pending = PendingAction(
            tool=tool_name,
            arguments=arguments,
            requested_text=requested_text,
            expires_at=datetime.now() + timedelta(seconds=settings.confirmation_timeout),
        )
        log.info("Staged pending action: %s %s", tool_name, arguments)
        return self.pending

    def pop_pending(self) -> PendingAction | None:
        pending = self.pending
        self.pending = None
        if pending is None or pending.expired():
            if pending is not None:
                log.info("Pending action expired: %s", pending.tool)
            return None
        return pending
