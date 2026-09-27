"""Ephemeral, session-local computer context used to resolve natural references."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any
@dataclass
class SessionContext:
    active_application: str = ""
    active_window: str = ""
    active_browser: str = ""
    active_chrome_profile: str = ""
    active_url: str = ""
    active_project: str = ""
    active_editor: str = ""
    last_downloaded_file: str = ""
    last_generated_prompt: str = ""
    last_task: str = ""
    current_task: str = ""
    current_directory: str = ""
    active_browser_tab: str = ""
    last_executed_prompt: str = ""
    last_action: str = ""
    last_verification: str = ""
    task_status: str = "IDLE"
    facts: dict[str, str] = field(default_factory=dict)

    def update(self, **values: Any) -> None:
        for key, value in values.items():
            if hasattr(self, key) and value not in (None, ""):
                setattr(self, key, str(value))

    def remember(self, key: str, value: str) -> None:
        if value:
            self.facts[key] = value
    def snapshot(self) -> dict[str, Any]:
        return asdict(self)

    def resolve(self, reference: str) -> str:
        """Resolve only known, non-secret contextual references."""
        key = reference.lower().strip()
        aliases = {
            "it": self.last_downloaded_file or self.active_application,
            "open it": self.last_downloaded_file or self.active_application,
            "open the downloaded file": self.last_downloaded_file,
            "downloaded file": self.last_downloaded_file,
            "this": self.active_window or self.active_application,
            "this file": self.last_downloaded_file,
            "that file": self.last_downloaded_file,
            "there": self.active_url or self.active_project,
            "that project": self.active_project,
            "the project": self.active_project,
            "that prompt": self.last_generated_prompt,
            "the previous prompt": self.last_generated_prompt,
            "the executed prompt": self.last_executed_prompt,
            "the downloaded file": self.last_downloaded_file,
            "the current project": self.active_project,
            "this project": self.active_project,
        }
        return aliases.get(key, self.facts.get(key, ""))
