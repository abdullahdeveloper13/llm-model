"""Permission system + confirmation flow + blocked tools."""
from __future__ import annotations

import pytest

from app.agent.permissions import BLOCKED_TOOLS, PermissionManager
from app.agent.registry import ToolRegistry


def test_safe_tool_allowed_without_confirmation() -> None:
    pm = PermissionManager()
    decision = pm.check(_tool_of("open_app", "safe"))
    assert decision.allowed and not decision.needs_confirmation


def test_confirmation_tools_need_confirmation() -> None:
    pm = PermissionManager()
    for name in ("shutdown", "restart", "whatsapp_call", "delete_file"):
        decision = pm.check(_tool_of(name, "confirmation"))
        assert decision.allowed and decision.needs_confirmation


def test_blocked_tool_names_are_refused() -> None:
    pm = PermissionManager()
    for name in BLOCKED_TOOLS:
        decision = pm.check(_tool_of(name, "safe"))
        assert not decision.allowed


def test_pending_action_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agent.permissions as perms

    monkeypatch.setattr(perms.settings, "confirmation_timeout", 0)
    pm = PermissionManager()
    pm.stage("shutdown", {}, "shutdown my computer")
    assert pm.pop_pending() is None  # already expired


def test_pending_action_survives_within_timeout() -> None:
    pm = PermissionManager()
    pm.stage("shutdown", {}, "shutdown my computer")
    pending = pm.pop_pending()
    assert pending is not None and pending.tool == "shutdown"
    assert pm.pop_pending() is None  # consumed once


class _FakeTool:
    def __init__(self, name: str, category: str) -> None:
        self.name = name
        self.category = category


def _tool_of(name: str, category: str) -> _FakeTool:
    return _FakeTool(name, category)


def test_registry_has_no_shell_tool(registry: ToolRegistry) -> None:
    assert "run_shell" not in registry.names()
    assert "shutdown" in registry.names()
    assert "open_app" in registry.names()
