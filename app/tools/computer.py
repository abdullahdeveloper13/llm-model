
"""Linux-first computer control abstraction with safe optional backends."""
from __future__ import annotations
import os, platform, shutil, subprocess
from dataclasses import asdict, dataclass
from typing import Any

from app.tools.base import Tool, ToolResult
@dataclass
class WindowInfo:
    title: str
    application: str = ""
    active: bool = False
class ComputerController:
    def _run(self, *args: str) -> bool:
        try: subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); return True
        except (OSError, subprocess.SubprocessError): return False
    def windows(self) -> list[WindowInfo]:
        if platform.system() != "Linux" or not shutil.which("wmctrl"): return []
        try:
            rows = subprocess.check_output(["wmctrl", "-l"], text=True, stderr=subprocess.DEVNULL).splitlines()
            return [WindowInfo(title=" ".join(row.split()[4:])) for row in rows if len(row.split()) >= 5]
        except (OSError, subprocess.SubprocessError): return []
    def active_window(self) -> WindowInfo | None:
        if platform.system() == "Linux" and shutil.which("xdotool"):
            try: return WindowInfo(subprocess.check_output(["xdotool", "getactivewindow", "getwindowname"], text=True).strip(), active=True)
            except (OSError, subprocess.SubprocessError): pass
        return next((w for w in self.windows() if w.active), None)
    def focus(self, title: str) -> bool:
        if platform.system() == "Linux" and shutil.which("wmctrl"): return self._run("wmctrl", "-a", title)
        return False
    def type_text(self, text: str) -> bool:
        if shutil.which("xdotool"): return self._run("xdotool", "type", "--clearmodifiers", text)
        return False
    def press(self, *keys: str) -> bool:
        if shutil.which("xdotool"): return self._run("xdotool", "key", "+".join(keys))
        return False
    def screenshot(self, path: str) -> bool:
        if shutil.which("gnome-screenshot"): return self._run("gnome-screenshot", "-f", path)
        if shutil.which("import"): return self._run("import", "-window", "root", path)
        return False
    def capabilities(self) -> dict[str, Any]:
        return {"platform": platform.system(), "wmctrl": bool(shutil.which("wmctrl")), "xdotool": bool(shutil.which("xdotool")), "screenshot": bool(shutil.which("gnome-screenshot") or shutil.which("import"))}


class ComputerControlTool(Tool):
    """Tool adapter over the existing Linux-first ComputerController."""

    name = "computer_control"
    description = "Control available Linux windows, keyboard input, and screenshots through structured desktop utilities."
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "windows, active_window, focus, type, press, screenshot, or capabilities"},
            "title": {"type": "string"},
            "text": {"type": "string"},
            "keys": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["action"],
    }
    category = "safe"

    def __init__(self, controller: ComputerController | None = None) -> None:
        self.controller = controller or ComputerController()

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "")).strip().lower()
        title = str(kwargs.get("title", "")).strip()
        if action == "windows":
            return ToolResult.ok("Windows inspected.", windows=[window.__dict__ for window in self.controller.windows()], verified=True)
        if action == "active_window":
            window = self.controller.active_window()
            return ToolResult.ok("Active window inspected.", window=window.__dict__ if window else None, verified=window is not None)
        if action == "capabilities":
            return ToolResult.ok("Computer capabilities inspected.", capabilities=self.controller.capabilities(), verified=True)
        if action == "focus":
            ok = self.controller.focus(title)
        elif action == "type":
            ok = self.controller.type_text(str(kwargs.get("text", "")))
        elif action == "press":
            keys = [part for part in str(kwargs.get("keys", "")).replace("+", " ").split() if part]
            ok = bool(keys) and self.controller.press(*keys)
        elif action == "screenshot":
            path = str(kwargs.get("path", "screenshot.png"))
            ok = self.controller.screenshot(path)
        else:
            return ToolResult.fail(f"Computer action '{action}' is not supported.", verified=False)
        return (ToolResult.ok(f"Computer action {action} complete.", verified=True)
                if ok else ToolResult.fail(f"Computer action {action} is unavailable or failed.", verified=False))
