"""Cross-platform application launch and window controls."""
from __future__ import annotations
import os
import platform
import subprocess
import shutil

from app.tools.apps.detector import AppDetector
from app.tools.base import Tool, ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)


class AppLauncher(Tool):
    name = "open_app"
    description = "Open an installed application by its discovered desktop name."
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
            if platform.system() == "Linux" and path.suffix.lower() == ".desktop":
                entry = self.detector._desktop_entry(path)
                command = self.detector.exec_command(entry[1]) if entry else []
                if not command or not shutil.which(command[0]):
                    return ToolResult.fail(f"The executable for {app.title()} is unavailable.")
                subprocess.Popen(command, close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif platform.system() == "Windows" and path.suffix.lower() == ".lnk":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                kwargs = {"close_fds": True}
                if platform.system() == "Windows":
                    kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen([str(path)], **kwargs)
            log.info("Launched %s -> %s", app, path)
            return ToolResult.ok(f"Opening {app.title()}.", path=str(path), verified=path.exists())
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
            if platform.system() == "Linux":
                from app.tools.computer import ComputerController
                if ComputerController().close(app):
                    return ToolResult.ok(f"{app.title()} is closed.")
                return ToolResult.fail(f"I couldn't find an open window for {app.title()}.")
            from pywinauto import Desktop
            windows = Desktop(backend="uia").windows(title_re=f"(?i).*{app}.*")
            if not windows:
                return ToolResult.fail(f"I couldn't find an open window for {app.title()}.")
            windows[0].close()
            return ToolResult.ok(f"{app.title()} is closed.")
        except ImportError:
            return ToolResult.fail("Window control dependencies are not installed.")
        except Exception as exc:
            return ToolResult.fail(f"I couldn't close {app.title()}. ({exc})")
