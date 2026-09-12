"""Validated keyboard tools. No shell or coordinate-based automation is used."""
from __future__ import annotations

from app.tools.base import Tool, ToolResult


KEY_ALIASES = {"escape": "esc", "return": "enter", "control": "ctrl", "spacebar": "space"}


def _backend():
    try:
        import pyautogui
        return pyautogui
    except ImportError as exc:
        raise RuntimeError("Keyboard automation needs pyautogui on Windows.") from exc


class TypeTextTool(Tool):
    name = "type_text"
    description = "Type validated text into the currently focused field."
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        text = str(kwargs.get("text", ""))
        if not text:
            return ToolResult.fail("There is no text to type.")
        try:
            _backend().write(text, interval=0.01)
            return ToolResult.ok("Text entered.")
        except Exception as exc:
            return ToolResult.fail(f"I couldn't type into the focused field. ({exc})")


class PressKeysTool(Tool):
    name = "press_keys"
    description = "Press one key or a validated hotkey such as ctrl+c, ctrl+v, enter, tab, escape, backspace, or alt+tab."
    schema = {"type": "object", "properties": {"keys": {"type": "array"}}, "required": ["keys"]}
    category = "safe"

    def validate(self, kwargs: dict) -> dict:
        keys = kwargs.get("keys", [])
        if isinstance(keys, str):
            keys = keys.replace("+", " ").split()
        normalized = [KEY_ALIASES.get(str(k).lower().strip(), str(k).lower().strip()) for k in keys]
        allowed = {"ctrl", "alt", "shift", "win", "enter", "tab", "esc", "backspace", "space", "c", "v", "a", "f4"}
        if not normalized or any(k not in allowed for k in normalized):
            raise ValueError("That key or hotkey is not allowed.")
        return {"keys": normalized}

    def execute(self, **kwargs) -> ToolResult:
        keys = self.validate(kwargs)["keys"]
        try:
            pyautogui = _backend()
            if len(keys) > 1:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(keys[0])
            return ToolResult.ok("Key pressed.")
        except Exception as exc:
            return ToolResult.fail(f"I couldn't press that key. ({exc})")
