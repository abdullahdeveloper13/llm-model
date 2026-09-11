"""Orchestrator: plans, enforces confirmation, executes, logs, answers.

This is the heart of the pipeline:
  text -> planner -> permission -> (confirmation?) -> executor -> response
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.agent.executor import Executor
from app.agent.permissions import PermissionManager
from app.agent.planner import Planner
from app.agent.registry import ToolRegistry
from app.config.settings import settings
from app.core.memory import Memory
from app.tools.base import ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)

YES_WORDS = {"yes", "yeah", "yep", "sure", "confirm", "confirmed", "do it", "go ahead"}
NO_WORDS = {"no", "nope", "cancel", "don't", "do not", "stop", "abort", "never mind"}

CONFIRM_PROMPTS = {
    "shutdown": "Are you sure you want to shut down your computer?",
    "restart": "Are you sure you want to restart your computer?",
    "whatsapp_call": "Should I start the WhatsApp call flow?",
    "delete_file": "Are you sure you want to delete that file?",
}


@dataclass
class TurnResult:
    response: str
    tool: str = ""
    tool_args: dict = field(default_factory=dict)
    success: bool = True
    awaiting_confirmation: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)

    def event(self, name: str, **data: Any) -> None:
        self.events.append({"event": name, **data})


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        memory: Memory | None = None,
    ) -> None:
        self.registry = registry or build_registry()
        self.permissions = PermissionManager()
        self.planner = Planner(self.registry)
        self.executor = Executor(self.registry, self.permissions)
        self.memory = memory
        #: optional callback receiving (event_name, payload) — used by the API
        self.on_event: Callable[[str, dict], None] | None = None

    # ---- main entry point -------------------------------------------------
    def handle(self, user_text: str) -> TurnResult:
        log.info("Handle: %r", user_text)
        self._emit("thinking")

        # 1) pending confirmation?
        confirmation = self._handle_confirmation(user_text)
        if confirmation is not None:
            return confirmation

        # 2) plan
        try:
            decision = self.planner.plan(user_text, self.memory.history if self.memory else None)
        except Exception:
            log.exception("Planner failed")
            return TurnResult(response="Something went wrong while understanding that request.")

        if decision.type == "conversation":
            self._remember(user_text, decision.response, "conversation", "", {}, decision.response, "ok")
            return TurnResult(response=decision.response)

        # 3) tool call -> permission gate
        tool = self.registry.get(decision.tool)
        if tool is None:  # should not happen after planner validation
            return TurnResult(response="That action isn't available.")

        perm = self.permissions.check(tool)
        if perm.needs_confirmation:
            prompt = CONFIRM_PROMPTS.get(
                decision.tool, f"Are you sure you want to {decision.tool.replace('_', ' ')}?"
            )
            self.permissions.stage(decision.tool, decision.arguments, user_text)
            self._remember(user_text, prompt, "confirmation", decision.tool, decision.arguments, "", "pending")
            self._emit("awaiting_confirmation", tool=decision.tool)
            return TurnResult(
                response=prompt,
                tool=decision.tool,
                tool_args=decision.arguments,
                awaiting_confirmation=True,
            )

        return self._run_tool(user_text, decision.tool, decision.arguments)

    # ---- internals ---------------------------------------------------------
    def _handle_confirmation(self, user_text: str) -> TurnResult | None:
        t = user_text.lower().strip()
        if not self.permissions.pending:
            return None
        if not (t in YES_WORDS or t in NO_WORDS):
            return None  # not a yes/no — treat as a new command

        pending = self.permissions.pop_pending()
        if t in NO_WORDS:
            log.info("User cancelled pending %s", pending.tool)
            self._remember(
                pending.requested_text, "Cancelled.", "conversation", pending.tool,
                pending.arguments, "Cancelled.", "cancelled",
            )
            return TurnResult(response="Cancelled.", tool=pending.tool, success=True)
        return self._run_tool(pending.requested_text, pending.tool, pending.arguments)

    def _run_tool(self, user_text: str, tool_name: str, arguments: dict) -> TurnResult:
        self._emit("tool_started", tool=tool_name)
        result = self.executor.execute(tool_name, arguments)
        self._emit("tool_completed" if result.success else "tool_failed", tool=tool_name, success=result.success)
        status = "ok" if result.success else "failed"
        self._remember(user_text, result.message, "tool_call", tool_name, arguments, result.message, status)
        return TurnResult(response=result.message, tool=tool_name, tool_args=arguments, success=result.success)

    def _remember(self, user_text: str, response: str, intent: str, tool: str,
                  arguments: dict, result: str, status: str) -> None:
        if self.memory:
            self.memory.remember_turn(user_text, response)
            try:
                self.memory.log_command(user_text, intent, tool, arguments, result, status)
            except Exception as exc:
                log.error("Failed to persist command: %s", exc)

    def _emit(self, event: str, **data: Any) -> None:
        if self.on_event:
            try:
                self.on_event(event, data)
            except Exception as exc:
                log.error("Event callback failed: %s", exc)


def build_registry() -> ToolRegistry:
    from app.agent.registry import build_default_registry

    return build_default_registry()
