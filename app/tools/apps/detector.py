"""Discovers installed applications from Start Menu shortcuts and PATH.

Windows exposes installed apps as .lnk shortcuts under:
  - %ProgramData%/Microsoft/Windows/Start Menu/Programs
  - %AppData%/Microsoft/Windows/Start Menu/Programs
We index those (no extra dependencies) and allow user overrides via a JSON file.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)

_START_MENU_DIRS = [
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

# Sensible aliases so common names resolve even if the .lnk is named differently.
KNOWN_ALIASES: dict[str, list[str]] = {
    "whatsapp": ["whatsapp"],
    "chrome": ["chrome", "google chrome"],
    "edge": ["edge", "microsoft edge"],
    "firefox": ["firefox", "mozilla firefox"],
    "code": ["visual studio code", "vs code", "code"],
    "notepad": ["notepad"],
    "calculator": ["calculator", "calculator app"],
    "explorer": ["file explorer", "explorer"],
    "word": ["word", "microsoft word"],
    "excel": ["excel", "microsoft excel"],
    "spotify": ["spotify"],
    "terminal": ["terminal", "windows terminal"],
}


class AppDetector:
    """Builds a name -> shortcut-path index once per session."""

    def __init__(self) -> None:
        self._index: dict[str, Path] = {}

    @property
    def index(self) -> dict[str, Path]:
        if not self._index:
            self._build()
        return self._index

    def _build(self) -> None:
        index: dict[str, Path] = {}
        for base in _START_MENU_DIRS:
            if not base.exists():
                continue
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if f.lower().endswith((".lnk", ".exe")):
                        stem = Path(f).stem.lower()
                        index.setdefault(stem, Path(root) / f)
        # user overrides from config JSON (app_shortcuts.json): {"name": "C:\\path"}
        override_file = settings.app_shortcuts_path or str(settings.data_dir / "app_shortcuts.json")
        if os.path.exists(override_file):
            import json

            try:
                overrides: dict[str, str] = json.loads(Path(override_file).read_text("utf-8"))
                for name, path in overrides.items():
                    p = Path(path)
                    if p.exists():
                        index[name.lower()] = p
            except Exception as exc:
                log.warning("Could not parse app shortcuts file %s: %s", override_file, exc)
        self._index = index
        log.info("App detector indexed %d shortcuts", len(index))

    def find(self, name: str) -> Path | None:
        """Resolve a friendly app name to a launchable path, or None."""
        key = name.lower().strip()
        index = self.index

        # exact / alias match against shortcut stems
        for alias in KNOWN_ALIASES.get(key, [key]):
            if alias in index:
                return index[alias]
        # substring match (e.g. "whatsapp" -> "whatsapp desktop.lnk")
        for stem, path in index.items():
            if key in stem:
                return path
        # fallback: on PATH (e.g. code.cmd)
        from shutil import which

        hit = which(name)
        return Path(hit) if hit else None
