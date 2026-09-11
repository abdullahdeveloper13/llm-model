"""Media control via Windows virtual key codes (no extra dependencies)."""
from __future__ import annotations

import ctypes

from app.tools.base import Tool, ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)

VK = {
    "play": 0xB3, "stop": 0xB2, "next": 0xB0, "previous": 0xB1,
    "mute": 0xAD, "volup": 0xAF, "voldown": 0xAE,
}
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def _press(vk: int) -> None:
    extra = ctypes.POINTER(ctypes.c_ulong)()
    for flags in (KEYEVENTF_EXTENDEDKEY, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP):
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", type(extra))]

        class INPUT(ctypes.Structure):
            class _I(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("i",)
            _fields_ = [("type", ctypes.c_ulong), ("i", _I)]

        inp = INPUT()
        inp.type = 1
        inp.ki = KEYBDINPUT(vk, 0, flags, 0, extra)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class MediaControlTool(Tool):
    name = "media_control"
    description = "Control system media: play, pause, next, previous, mute, volume up, volume down."
    schema = {
        "type": "object",
        "properties": {"action": {"type": "string", "description": "play|pause|next|previous|mute|volume_up|volume_down"}},
        "required": ["action"],
    }
    category = "safe"

    ACTIONS = {
        "play": "play", "pause": "play", "next": "next", "previous": "previous",
        "mute": "mute", "volume_up": "volup", "volume_down": "voldown",
    }

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action", "")).strip().lower().replace(" ", "_")
        vk = VK.get(self.ACTIONS.get(action, ""))
        if vk is None:
            return ToolResult.fail(f"I don't know the media action '{action}'.")
        try:
            _press(vk)
            log.info("Media key sent: %s", action)
            return ToolResult.ok(f"{action.replace('_', ' ').capitalize()}.")
        except Exception as exc:
            log.error("Media control failed: %s", exc)
            return ToolResult.fail(f"I couldn't control media playback. ({exc})")
