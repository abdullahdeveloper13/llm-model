"""Planner: routes user text through the brain (LLM -> rule fallback) and
validates that the requested tool exists and its arguments type-check."""
from __future__ import annotations

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
            decision = self._validate(decision, user_text)
        log.info("Plan: type=%s tool=%s args=%s", decision.type, decision.tool, decision.arguments)
        return decision

    def _decide(self, user_text: str, history: list[dict[str, str]] | None) -> BrainDecision:
        if self.llm_brain is not None:
            try:
                return self.llm_brain.decide(user_text, history)
            except Exception as exc:
                log.warning("LLM brain failed, falling back to rules: %s", exc)
        return self.rule_brain.decide(user_text, history)

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
