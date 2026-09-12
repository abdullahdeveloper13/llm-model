"""Window operations through Windows UI Automation, without coordinates."""
from __future__ import annotations

from app.tools.base import Tool, ToolResult


class WindowControlTool(Tool):
    name = "window_control"
    description = "Minimize, maximize, focus, or list application windows through UI Automation."
    schema = {"type": "object", "properties": {"action": {"type": "string"}, "application": {"type": "string"}}, "required": ["action"]}
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action", "")).lower().strip()
        application = str(kwargs.get("application", "")).lower().strip()
        try:
            from pywinauto import Desktop
            windows = [w for w in Desktop(backend="uia").windows() if w.window_text().strip()]
            if action == "list":
                return ToolResult.ok("Open windows: " + ", ".join(w.window_text() for w in windows), windows=[w.window_text() for w in windows])
            matches = [w for w in windows if application in w.window_text().lower()]
            if not matches:
                return ToolResult.fail(f"I couldn't find an open window for {application or 'that application'}.")
            window = matches[0]
            if action == "minimize":
                window.minimize()
            elif action == "maximize":
                window.maximize()
            elif action in {"switch", "focus"}:
                window.set_focus()
            else:
                return ToolResult.fail("That window action is not supported.")
            return ToolResult.ok(f"Window {action} complete.")
        except ImportError:
            return ToolResult.fail("Window controls need pywinauto on Windows.")
        except Exception as exc:
            return ToolResult.fail(f"Window control failed. ({exc})")
