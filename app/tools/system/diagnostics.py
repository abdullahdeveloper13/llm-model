"""Safe, read-only diagnostics for the local voice agent."""
from __future__ import annotations
import importlib.util
import os
import platform
import shutil
from pathlib import Path
from app.tools.base import Tool, ToolResult

class DiagnosticsTool(Tool):
    name = "run_diagnostics"
    description = "Inspect local voice, computer-control, browser, app, and filesystem capabilities."
    schema = {"type": "object", "properties": {}}
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        from app.tools.apps.chrome import ChromeManager
        from app.tools.apps.chrome_profiles import ChromeProfileManager
        from app.tools.apps.detector import AppDetector
        from app.tools.computer import ComputerController
        mic = self._module("sounddevice")
        stt = self._module("faster_whisper")
        tts = self._module("pyttsx3")
        chrome = ChromeManager()
        diagnostics = {
            "os": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
            "python": platform.python_version(),
            "voice": {"microphone_library": mic, "speech_recognition_library": stt, "tts_library": tts},
            "browser_automation": {"playwright_library": self._module("playwright"), "download_directory": str(Path.home() / "Downloads")},
            "editors": {"cursor": bool(shutil.which("cursor")), "vscode": bool(shutil.which("code"))},
            "computer": ComputerController().capabilities(),
            "browsers": {"chrome_executable": chrome.executable(), "profiles": [p.as_dict() for p in ChromeProfileManager().discover()]},
            "applications": {"count": len(AppDetector().discover())},
            "filesystem": {"home": str(Path.home()), "downloads": str(Path.home() / "Downloads"), "downloads_exists": (Path.home() / "Downloads").is_dir()},
            "dependencies": {name: bool(shutil.which(name)) for name in ("wmctrl", "xdotool", "xdg-open")},
            "display": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        }
        available = sum(bool(value) for value in diagnostics["voice"].values())
        return ToolResult.ok(f"Diagnostics complete: {available}/3 voice components are available.", diagnostics=diagnostics)

    @staticmethod
    def _module(name: str) -> bool:
        return importlib.util.find_spec(name) is not None
