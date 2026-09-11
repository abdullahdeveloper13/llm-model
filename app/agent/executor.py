"""Executor: the ONLY component that actually runs tools."""
from __future__ import annotations

from app.agent.permissions import PermissionManager
from app.agent.registry import ToolRegistry
from app.config.settings import settings
from app.tools.base import ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)

SIMULATE_IN_DEV = {"shutdown", "restart"}


class Executor:
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager) -> None:
        self.registry = registry
        self.permissions = permissions

    def execute(self, tool_name: str, arguments: dict) -> ToolResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            log.warning("Executor refused unknown tool: %s", tool_name)
            return ToolResult.fail("That operation isn't registered. Refusing to run it.")

        decision = self.permissions.check(tool)
        if not decision.allowed:
            return ToolResult.fail(decision.reason)

        if not settings.is_production and tool_name in SIMULATE_IN_DEV:
            log.info("Dev-mode simulation for %s", tool_name)
            return ToolResult.ok(f"[SIMULATION] {tool_name} command would execute.")

        try:
            result = tool.execute(**arguments)
            log.info("Tool %s -> success=%s", tool_name, result.success)
            return result
        except Exception as exc:  # never crash the assistant on one tool
            log.exception("Tool %s crashed", tool_name)
            return ToolResult.fail(f"The operation failed unexpectedly. ({exc})")
