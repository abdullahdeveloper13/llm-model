"""Orchestrator: plans, enforces confirmation, executes, logs, answers.

This is the heart of the pipeline:
  text -> planner -> permission -> (confirmation?) -> executor -> response
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from pathlib import Path

from app.agent.executor import Executor
from app.agent.permissions import PermissionManager
from app.agent.prompts import PromptManager, PromptStatus
from app.agent.planner import Planner
from app.agent.registry import ToolRegistry
from app.config.settings import settings
from app.core.context import SessionContext
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
        prompt_runner: Callable[[str], str] | None = None,
    ) -> None:
        self.registry = registry or build_registry()
        self.permissions = PermissionManager()
        self.planner = Planner(self.registry)
        self.executor = Executor(self.registry, self.permissions)
        self.memory = memory
        self.prompt_manager = PromptManager()
        self.prompt_runner = prompt_runner
        self.context = SessionContext()
        self.last_task: dict[str, Any] | None = None
        #: optional callback receiving (event_name, payload) — used by the API
        self.on_event: Callable[[str, dict], None] | None = None

    def reset_session(self) -> None:
        """Clear ephemeral context while retaining the command audit trail."""
        self.planner.rule_brain.reset()

    # ---- main entry point -------------------------------------------------
    def handle(self, user_text: str) -> TurnResult:
        log.info("Handling assistant request")
        self._emit("thinking")

        if self.prompt_manager.is_write_request(user_text):
            state = self.prompt_manager.create(user_text)
            self.context.update(last_generated_prompt=state.generated_prompt, last_task=user_text, last_action="prompt_write", task_status="COMPLETED")
            response = f"Prompt {state.id} is ready. I did not execute it.\n\n{state.generated_prompt}"
            self._remember(user_text, response, "prompt_write", "", {}, state.generated_prompt, "ok")
            return TurnResult(response=response, success=True, events=[{"event": "prompt_state", "id": state.id, "status": state.status}])
        if self.prompt_manager.is_execute_request(user_text):
            if self.prompt_manager.latest is None:
                return TurnResult(response="There is no READY prompt to execute.", success=False)
            return self._execute_prompt(user_text)

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
            if not decision.sensitive:
                self._remember(user_text, decision.response, "conversation", "", {}, decision.response, "ok")
            return TurnResult(response=decision.response)

        # 3) Resolve contextual references before permission/execution.
        if decision.steps:
            decision.steps = [{"tool": step["tool"], "arguments": self._resolve_arguments(step["tool"], step.get("arguments", {}))} for step in decision.steps]
            return self._run_steps(user_text, decision.steps, decision.sensitive)
        decision.arguments = self._resolve_arguments(decision.tool, decision.arguments)

        # 4) single tool call -> permission gate
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

        return self._run_tool(user_text, decision.tool, decision.arguments, remember=not decision.sensitive)

    # ---- internals ---------------------------------------------------------
    def _resolve_arguments(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        resolved = dict(arguments)
        if tool_name == "open_app" and str(resolved.get("application", "")).lower() in {"it", "this", "that"}:
            reference = self.context.resolve(str(resolved["application"]))
            if reference and Path(reference).is_file():
                return {"path": reference, "action": "open"}
        if tool_name == "file_operation" and str(resolved.get("path", "")).lower() in {"it", "this", "that", "the downloaded file"}:
            resolved["path"] = self.context.resolve(str(resolved["path"]))
        if tool_name in {"open_editor", "run_project_tests"} and not str(resolved.get("project", "")).strip():
            resolved["project"] = self.context.active_project or str(Path.cwd())
        if tool_name == "open_editor" and str(resolved.get("project", "")).lower() in {"this project", "the current project"}:
            resolved["project"] = self.context.active_project or str(Path.cwd())
        if tool_name == "open_chrome" and not str(resolved.get("profile", "")).strip() and self.context.active_chrome_profile:
            resolved["profile"] = self.context.active_chrome_profile
        return resolved

    def _execute_prompt(self, user_text: str) -> TurnResult:
        # The core has no editor-specific side effects. Integrators inject an
        # agent runner; by default we preserve the exact prompt and report the
        # missing platform capability honestly.
        if self.prompt_runner is None:
            return TurnResult(response="No coding-agent runner is configured; the READY prompt was not executed.", success=False)
        state = self.prompt_manager.execute(self.prompt_runner)
        if state.status == PromptStatus.COMPLETED:
            message = f"Prompt {state.id} execution finished: {state.result}"
            self.context.update(last_executed_prompt=state.generated_prompt, last_action="prompt_execute", last_verification="runner returned", task_status="COMPLETED")
            self._remember(user_text, message, "prompt_execute", "", {}, state.result, "ok")
            return TurnResult(response=message, success=True, events=[{"event": "prompt_state", "id": state.id, "status": state.status}])
        return TurnResult(response=f"Prompt execution failed: {state.result}", success=False)

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

    def _run_steps(self, user_text: str, steps: list[dict], sensitive: bool = False) -> TurnResult:
        # Validate every step's permission before executing any step, so a later
        # destructive action cannot hide behind earlier safe actions.
        for step in steps:
            tool = self.registry.get(step["tool"])
            if tool is None:
                return TurnResult(response=f"Step '{step['tool']}' is not registered.", success=False)
            decision = self.permissions.check(tool)
            if decision.needs_confirmation:
                prompt = CONFIRM_PROMPTS.get(step["tool"], "Are you sure you want to do that?")
                self.permissions.stage(step["tool"], step.get("arguments", {}), user_text)
                return TurnResult(response=prompt, tool=step["tool"], tool_args=step.get("arguments", {}), awaiting_confirmation=True)
        messages: list[str] = []
        for index, step in enumerate(steps, 1):
            result = self._run_tool(user_text, step["tool"], step.get("arguments", {}), remember=not sensitive)
            if not result.success:
                return TurnResult(response=f"Step {index} failed: {result.response}", tool=result.tool, tool_args=result.tool_args, success=False)
            messages.append(result.response)
        return TurnResult(response=messages[-1] if messages else "Done.", success=True)

    def _run_tool(self, user_text: str, tool_name: str, arguments: dict, remember: bool = True) -> TurnResult:
        self._emit("tool_started", tool=tool_name)
        result = self.executor.execute(tool_name, arguments)
        self.context.update(last_task=user_text, current_task="", last_action=tool_name, task_status="COMPLETED" if result.success else "FAILED", last_verification=str(result.data.get("verified", result.success)))
        self.last_task = {"goal": user_text, "tool": tool_name, "arguments": arguments, "status": "COMPLETED" if result.success else "FAILED", "result": result.message, "verified": result.data.get("verified", result.success)}
        if result.success:
            if tool_name in {"open_app", "open_chrome", "open_website"}:
                self.context.update(active_application=arguments.get("application", "Chrome" if tool_name == "open_chrome" else ""), active_browser="Chrome" if tool_name == "open_chrome" else "", active_url=result.data.get("url", ""))
            if tool_name == "open_chrome" and result.data.get("profile"):
                self.context.update(active_chrome_profile=result.data["profile"].get("name", ""))
            if tool_name in {"search_files", "browser_control"} and result.data.get("files"):
                self.context.update(last_downloaded_file=result.data["files"][0])
            if tool_name == "browser_control" and result.data.get("path"):
                self.context.update(last_downloaded_file=result.data["path"])
            if tool_name == "browser_control":
                state = result.data.get("state", {})
                self.context.update(active_browser="Chrome", active_url=state.get("url", ""), active_window=state.get("title", ""), active_browser_tab=state.get("title", ""))
            if tool_name == "open_editor":
                self.context.update(active_editor=result.data.get("editor", arguments.get("editor", "")), active_project=result.data.get("project", arguments.get("project", "")), current_directory=result.data.get("project", arguments.get("project", "")))
        self._emit("tool_completed" if result.success else "tool_failed", tool=tool_name, success=result.success)
        status = "ok" if result.success else "failed"
        if remember:
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
