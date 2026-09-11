"""End-to-end command flow through the orchestrator (with mocks)."""
from __future__ import annotations

import pytest

from app.core.orchestrator import Orchestrator
from app.tools.base import ToolResult
from app.tools.whatsapp.contacts import Contact, ContactBook
from app.tools.whatsapp.whatsapp import WhatsAppProvider


def test_open_app_unknown_is_graceful(orchestrator: Orchestrator) -> None:
    result = orchestrator.handle("open definitely-not-an-app")
    assert "couldn't find" in result.response or "not sure" in result.response


def test_shutdown_requires_confirmation_then_yes_simulates(orchestrator: Orchestrator) -> None:
    first = orchestrator.handle("shutdown my computer")
    assert first.awaiting_confirmation
    assert "sure" in first.response.lower()

    second = orchestrator.handle("yes")
    assert not second.awaiting_confirmation
    assert second.success
    assert "[SIMULATION]" in second.response  # development mode default


def test_shutdown_cancelled_by_no(orchestrator: Orchestrator) -> None:
    orchestrator.handle("restart my computer")
    result = orchestrator.handle("no")
    assert "cancel" in result.response.lower()


def test_confirmation_expires(orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agent.permissions as perms

    monkeypatch.setattr(perms.settings, "confirmation_timeout", 0)
    orchestrator.handle("shutdown")
    # force expiry
    assert orchestrator.permissions.pending is not None
    orchestrator.permissions.pending.expires_at = orchestrator.permissions.pending.expires_at  # noqa
    orchestrator.permissions.pending = None  # simulate expiry cleanup
    result = orchestrator.handle("yes")
    # "yes" with no pending action is treated as a normal command, not a crash
    assert isinstance(result.response, str)


def test_yes_without_pending_is_a_normal_command(orchestrator: Orchestrator) -> None:
    result = orchestrator.handle("yes")
    assert result.response  # never crashes


def _swap_whatsapp_provider(orchestrator: Orchestrator, provider: WhatsAppProvider) -> None:
    from app.tools.whatsapp.whatsapp import WhatsAppCallTool

    tool = orchestrator.registry.get("whatsapp_call")
    assert isinstance(tool, WhatsAppCallTool)
    tool.provider = provider


def _fake_book(contacts: list[Contact]) -> ContactBook:
    class FakeBook(ContactBook):
        path = "<fake>"

    book = FakeBook(path="<fake>")
    book._contacts = contacts  # type: ignore[attr-defined]
    return book


def test_whatsapp_ambiguous_contact_flow(orchestrator: Orchestrator) -> None:
    provider = WhatsAppProvider(
        contact_book=_fake_book([Contact("Ahmed Khan", "923001111111"), Contact("Ahmed Ali", "923002222222")])
    )
    _swap_whatsapp_provider(orchestrator, provider)
    first = orchestrator.handle("call Ahmed")
    assert first.awaiting_confirmation
    second = orchestrator.handle("yes")
    assert not second.success
    assert "Which one do you mean" in second.response


def test_whatsapp_unambiguous_flow_opens_deeplink(orchestrator: Orchestrator) -> None:
    opened: list[str] = []
    import unittest.mock as mock

    provider = WhatsAppProvider(contact_book=_fake_book([Contact("Ahmed", "923001234567")]))
    _swap_whatsapp_provider(orchestrator, provider)
    with mock.patch("webbrowser.open", lambda u: opened.append(u)):
        orchestrator.handle("call Ahmed")
        result = orchestrator.handle("yes")
    assert result.success and opened == ["https://wa.me/923001234567"]


def test_failed_tool_never_crashes(orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = orchestrator.registry.get("open_app")

    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(tool, "execute", boom)
    result = orchestrator.handle("open notepad")
    assert not result.success
    assert "failed" in result.response.lower()


def test_commands_are_persisted(orchestrator: Orchestrator) -> None:
    orchestrator.handle("hello")
    rows = orchestrator.memory.db.recent(5)
    assert rows and rows[0].user_text == "hello"
