"""Multi-step task lifecycle with observable progress and bounded recovery."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable
import uuid
class TaskStatus(str, Enum):
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    NEEDS_USER_INPUT = "NEEDS_USER_INPUT"
@dataclass
class Task:
    goal: str
    context: dict[str, Any] = field(default_factory=dict)
    plan: list[dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    observations: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PLANNING
    errors: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    def snapshot(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value
class TaskEngine:
    def __init__(self, executor: Callable[[dict[str, Any]], Any], verifier: Callable[[dict[str, Any], Any], bool] | None = None, max_retries: int = 1) -> None:
        self.executor, self.verifier, self.max_retries = executor, verifier, max_retries
        self.current: Task | None = None
    def run(self, goal: str, plan: list[dict[str, Any]], context: dict[str, Any] | None = None) -> Task:
        task = Task(goal=goal, context=context or {}, plan=plan)
        self.current = task
        task.status = TaskStatus.EXECUTING
        for index, step in enumerate(plan):
            task.current_step = index
            task.observations.append(f"Before step {index + 1}: {step.get('action', step.get('tool', 'action'))}")
            outcome = None
            for attempt in range(self.max_retries + 1):
                try:
                    outcome = self.executor(step)
                    if getattr(outcome, "success", True):
                        break
                    if attempt == self.max_retries:
                        raise RuntimeError(getattr(outcome, "message", "step failed"))
                except Exception as exc:
                    if attempt == self.max_retries:
                        task.errors.append(str(exc)); task.status = TaskStatus.FAILED; return task
            task.actions.append({"step": index, "result": getattr(outcome, "message", str(outcome))})
            task.status = TaskStatus.VERIFYING
            verified = True if self.verifier is None else self.verifier(step, outcome)
            if not verified:
                task.observations.append(f"Verification failed for step {index + 1}; attempting bounded recovery")
                recovered = False
                for attempt in range(self.max_retries):
                    try:
                        outcome = self.executor(step)
                        if getattr(outcome, "success", True) and self.verifier(step, outcome):
                            recovered = True
                            task.actions.append({"step": index, "recovery": attempt + 1, "result": getattr(outcome, "message", str(outcome))})
                            break
                    except Exception as exc:
                        task.errors.append(f"Recovery {attempt + 1}: {exc}")
                if not recovered:
                    task.errors.append(f"Verification failed for step {index + 1}")
                    task.status = TaskStatus.FAILED
                    return task
            task.verification.append(f"Step {index + 1} verified")
            task.status = TaskStatus.EXECUTING
        task.status = TaskStatus.COMPLETED
        return task
