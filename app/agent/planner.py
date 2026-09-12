"""Planner: routes user text through the brain (LLM -> rule fallback) and
validates that the requested tool exists and its arguments type-check."""
from __future__ import annotations

import re

from app.agent.registry import ToolRegistry
from app.core.brain import Brain, BrainDecision, LLMBrain, RuleBasedBrain
from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class Planner:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.llm_brain: Brain | None = LLMBrain(registry) if settings.llm_enabled else None
        self.rule_brain = RuleBasedBrain()

    def plan(self, user_text: str, history: list[dict[str, str]] | None = None) -> BrainDecision:
        decision = self._decide(user_text, history)
        if decision.type == "tool_call":
            if decision.steps:
                valid_steps: list[dict] = []
                for step in decision.steps:
                    checked = self._validate(BrainDecision(type="tool_call", tool=step["tool"], arguments=step.get("arguments", {})), user_text)
                    if checked.type != "tool_call":
                        return checked
                    valid_steps.append({"tool": checked.tool, "arguments": checked.arguments})
                decision.steps = valid_steps
            else:
                decision = self._validate(decision, user_text)
        if not decision.sensitive:
            log.info("Plan: type=%s tool=%s", decision.type, decision.tool)
        return decision

    def _decide(self, user_text: str, history: list[dict[str, str]] | None) -> BrainDecision:
        # Sensitive input must remain local even when an API key is configured.
        if self.rule_brain.sensitive_mode or re.search(r"\b(enter|type|dictate)\s+(pin|password|passcode|otp|code)\b", user_text, re.I):
            return self.rule_brain.decide(user_text, history)
        local = self.rule_brain.decide(user_text, history)
        if local.type == "tool_call" or local.response != "I'm not sure how to help with that.":
            return local
        if self.llm_brain is not None:
            try:
                decision = self.llm_brain.decide(user_text, history)
                if decision.type == "conversation" and decision.response.lstrip().startswith(("{", "[")):
                    return local
                return decision if decision.type == "tool_call" or decision.response else local
            except Exception as exc:
                log.warning("LLM brain failed, falling back to rules: %s", exc)
        return local

    def _validate(self, decision: BrainDecision, user_text: str) -> BrainDecision:
        tool = self.registry.get(decision.tool)
        if tool is None:
            log.warning("LLM requested unregistered tool: %s", decision.tool)
            return BrainDecision(
                type="conversation",
                response="That action isn't available. I can only perform registered operations.",
            )
        try:
            decision.arguments = tool.validate(dict(decision.arguments))
        except Exception as exc:
            log.warning("Invalid arguments for %s: %s", decision.tool, exc)
            return BrainDecision(
                type="conversation",
                response=f"I couldn't understand the details for that request. ({exc})",
            )
        return decision
