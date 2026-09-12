"""Launch Windows applications by name using discovered shortcuts."""
from __future__ import annotations

import os
import subprocess

from app.tools.apps.detector import AppDetector
from app.tools.base import Tool, ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)


class AppLauncher(Tool):
    name = "open_app"
    description = (
        "Open/launch an installed Windows application by name, e.g. 'whatsapp', "
        "'chrome', 'code', 'notepad', 'calculator'."
    )
    schema = {
        "type": "object",
        "properties": {
            "application": {"type": "string", "description": "App name, e.g. whatsapp"}
        },
        "required": ["application"],
    }
    category = "safe"

    def __init__(self, detector: AppDetector | None = None) -> None:
        self.detector = detector or AppDetector()

    def execute(self, **kwargs) -> ToolResult:
        app = str(kwargs.get("application", "")).strip()
        if not app:
            return ToolResult.fail("No application name was provided.")
        path = self.detector.find(app)
        if path is None:
            log.info("Application not found: %s", app)
            return ToolResult.fail(f"I couldn't find '{app}' installed on this computer.")

        try:
            if path.suffix.lower() == ".lnk":
                os.startfile(str(path))  # noqa: S606 - standard way to launch .lnk
            else:
                # CREATE_NO_WINDOW keeps a console from flashing
                subprocess.Popen(
                    [str(path)],
                    creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
                    close_fds=True,
                )
            log.info("Launched %s -> %s", app, path)
            return ToolResult.ok(f"Opening {app.title()}.", path=str(path))
        except Exception as exc:
            log.error("Failed to launch %s: %s", app, exc)
            return ToolResult.fail(f"I couldn't open {app.title()}. ({exc})")


class CloseAppTool(Tool):
    name = "close_app"
    description = "Close an application window by accessible title through Windows UI Automation."
    schema = {"type": "object", "properties": {"application": {"type": "string"}}, "required": ["application"]}
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        app = str(kwargs.get("application", "")).strip()
        if not app:
            return ToolResult.fail("No application name was provided.")
        try:
            from pywinauto import Desktop
            windows = Desktop(backend="uia").windows(title_re=f"(?i).*{app}.*")
            if not windows:
                return ToolResult.fail(f"I couldn't find an open window for {app.title()}.")
            windows[0].close()
            return ToolResult.ok(f"{app.title()} is closed.")
        except ImportError:
            return ToolResult.fail("Closing apps needs pywinauto on Windows.")
        except Exception as exc:
            return ToolResult.fail(f"I couldn't close {app.title()}. ({exc})")
