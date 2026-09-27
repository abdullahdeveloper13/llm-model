from __future__ import annotations
from pathlib import Path
from app.agent.prompts import PromptStatus
from app.core.orchestrator import Orchestrator
from app.storage.database import Database
from app.core.memory import Memory

def test_write_prompt_is_ready_and_has_no_execution_side_effect(tmp_path: Path) -> None:
    calls: list[str] = []
    orch = Orchestrator(memory=Memory(Database(str(tmp_path / "db.sqlite"))), prompt_runner=calls.append)
    result = orch.handle("Write a detailed prompt to audit my website")
    assert result.success
    assert orch.prompt_manager.latest is not None
    assert orch.prompt_manager.latest.status == PromptStatus.READY
    assert "USER GOAL" in orch.prompt_manager.latest.generated_prompt
    assert calls == []


def test_execute_prompt_uses_exact_stored_prompt(tmp_path: Path) -> None:
    received: list[str] = []
    orch = Orchestrator(memory=Memory(Database(str(tmp_path / "db.sqlite"))), prompt_runner=received.append)
    orch.handle("Create a prompt to fix the navbar")
    stored = orch.prompt_manager.latest.generated_prompt
    result = orch.handle("Execute this prompt")
    assert result.success
    assert received == [stored]
    assert orch.prompt_manager.latest.status == PromptStatus.COMPLETED

def test_execute_without_prompt_is_not_action(tmp_path: Path) -> None:
    calls: list[str] = []
    orch = Orchestrator(memory=Memory(Database(str(tmp_path / "db.sqlite"))), prompt_runner=calls.append)
    result = orch.handle("Execute this prompt")
    assert not result.success
    assert calls == []
