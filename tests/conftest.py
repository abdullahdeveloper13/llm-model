"""Shared fixtures: registry and orchestrator built without any hardware."""
from __future__ import annotations

import pytest

from app.agent.permissions import PermissionManager
from app.agent.registry import build_default_registry
from app.core.memory import Memory
from app.core.orchestrator import Orchestrator
from app.storage.database import Database


@pytest.fixture()
def registry() -> object:
    return build_default_registry()


@pytest.fixture()
def orchestrator(tmp_path) -> Orchestrator:
    db = Database(path=str(tmp_path / "test.db"))
    return Orchestrator(registry=build_default_registry(), memory=Memory(db))
