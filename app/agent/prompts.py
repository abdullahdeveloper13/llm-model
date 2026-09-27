'''Explicit prompt drafting and execution state.

Prompt creation is deliberately separate from execution: drafting only reads
allow-listed project context and stores a READY artifact. Execution requires a
later, explicit instruction and a caller supplied runner.
'''
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
class PromptStatus:
    DRAFT = "DRAFT"
    READY = "READY"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

@dataclass
class PromptState:
    id: str
    original_user_instruction: str
    generated_prompt: str
    project_context: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = PromptStatus.READY
    result: str = ""

class PromptManager:
    '''Owns the latest prompt artifact and its explicit lifecycle.'''


    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.latest: PromptState | None = None
    def is_write_request(self, text: str) -> bool:
        return bool(re.search(r"\b(write|create|prepare|draft|generate)\b.*\bprompt\b", text, re.I))

    def is_execute_request(self, text: str) -> bool:
        return bool(re.search(r"\b(execute|run)\b.*\b(this|the|that)?\s*prompt\b|\bnow execute it\b", text, re.I))

    def create(self, instruction: str) -> PromptState:
        context = self._safe_context()
        prompt = self._render(instruction, context)
        self.latest = PromptState(
            id=uuid.uuid4().hex,
            original_user_instruction=instruction,
            generated_prompt=prompt,
            project_context=context,
        )
        return self.latest
    def execute(self, runner: Callable[[str], str]) -> PromptState:
        if self.latest is None:
            raise ValueError("There is no stored prompt to execute.")
        if self.latest.status != PromptStatus.READY:
            raise ValueError(f"Prompt is {self.latest.status}, not READY.")
        self.latest.status = PromptStatus.EXECUTING
        try:
            self.latest.result = runner(self.latest.generated_prompt)
            self.latest.status = PromptStatus.COMPLETED
        except Exception as exc:
            self.latest.result = str(exc)
            self.latest.status = PromptStatus.FAILED
        return self.latest
    def _safe_context(self) -> dict[str, str]:
        context: dict[str, str] = {}
        for name in ("README.md", "AGENTS.md", "CLAUDE.md", "package.json", "pyproject.toml"):
            path = self.project_root / name
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                context[name] = text[:12000]
        source_dirs = [self.project_root / "app", self.project_root / "src", self.project_root / "tests"]
        context["source_structure"] = "\n".join(
            str(p.relative_to(self.project_root))
            for root in source_dirs if root.is_dir()
            for p in sorted(root.rglob("*")) if p.is_file()
        )[:12000]
        return context
    @staticmethod
    def _render(instruction: str, context: dict[str, str]) -> str:
        context_text = "\n\n".join(f"### {key}\n{value}" for key, value in context.items())
        return (
            "Act as a careful engineering agent. Fulfil the user's exact goal below without "
            "expanding scope. Inspect the existing project before changing anything, preserve "
            "working behavior, avoid secrets, and verify changes with relevant tests.\n\n"
            f"USER GOAL:\n{instruction.strip()}\n\n"
            "PROJECT CONTEXT (safe, non-secret excerpts):\n"
            f"{context_text or '(no project context was available)'}\n\n"
            "REPORT: summarize observed problems, files changed, verification performed, and "
            "any blockers."
        )
