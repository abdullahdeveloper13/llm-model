"""Validated browser navigation hotkeys."""
from __future__ import annotations

from app.tools.base import Tool, ToolResult


class BrowserNavigationTool(Tool):
    name = "browser_navigation"
    description = "Navigate browser history or manage a tab with a fixed set of validated actions."
    schema = {"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action", "")).lower().strip()
        hotkeys = {"back": ("alt", "left"), "forward": ("alt", "right"), "new_tab": ("ctrl", "t"), "close_tab": ("ctrl", "w")}
        if action not in hotkeys:
            return ToolResult.fail("That browser action is not supported.")
        try:
            import pyautogui
            pyautogui.hotkey(*hotkeys[action])
            return ToolResult.ok(f"Browser {action.replace('_', ' ')} complete.")
        except Exception as exc:
            return ToolResult.fail(f"Browser navigation failed. ({exc})")
