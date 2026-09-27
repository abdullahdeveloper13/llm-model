"""Discovers installed applications from Start Menu shortcuts and PATH.

Windows exposes installed apps as .lnk shortcuts under:
  - %ProgramData%/Microsoft/Windows/Start Menu/Programs
  - %AppData%/Microsoft/Windows/Start Menu/Programs
We index those (no extra dependencies) and allow user overrides via a JSON file.
"""
from __future__ import annotations

import configparser
import os
import platform
import shlex
import shutil
from pathlib import Path

from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)

_START_MENU_DIRS = [
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]
_LINUX_DESKTOP_DIRS = [
    Path.home() / ".local/share/applications",
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
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
        bases = _LINUX_DESKTOP_DIRS if platform.system() == "Linux" else _START_MENU_DIRS
        for base in bases:
            if not base.exists():
                continue
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if (platform.system() == "Linux" and f.lower().endswith(".desktop")) or (platform.system() != "Linux" and f.lower().endswith((".lnk", ".exe"))):
                        path = Path(root) / f
                        stem = Path(f).stem.lower()
                        if platform.system() == "Linux":
                            entry = self._desktop_entry(path)
                            if entry is None:
                                continue
                            name, exec_line = entry
                            index.setdefault(stem, path)
                            for display_name in name.split("\x00"):
                                if display_name:
                                    index.setdefault(display_name.lower(), path)
                            executable = self.exec_command(exec_line)[0] if self.exec_command(exec_line) else ""
                            if executable:
                                index.setdefault(f"{stem}::exec", Path(executable))
                        else:
                            index.setdefault(stem, path)
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
        log.info("App detector indexed %d applications", len(index))

    @staticmethod
    def _desktop_entry(path: Path) -> tuple[str, str] | None:
        try:
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read(path, encoding="utf-8")
            if not parser.has_section("Desktop Entry"):
                return None
            values = parser["Desktop Entry"]
            if values.get("Type", "Application") != "Application" or values.get("Hidden", "false").lower() == "true" or values.get("NoDisplay", "false").lower() == "true":
                return None
            command = values.get("Exec", "").strip()
            try:
                if values.get("TryExec") and not (Path(values["TryExec"]).exists() or shutil.which(values["TryExec"])):
                    return None
            except OSError:
                return None
            if not command:
                return None
            names = [values.get("Name", path.stem), values.get("GenericName", "")]
            names.extend(x.strip() for x in values.get("Categories", "").split(";") if x.strip())
            return "\x00".join(names), command
        except (OSError, configparser.Error):
            return None
    @staticmethod
    def exec_command(exec_line: str) -> list[str]:
        """Parse a desktop Exec line without shell evaluation."""
        try:
            parts = shlex.split(exec_line, posix=True)
        except ValueError:
            return []
        return [part for part in parts if not part.startswith("%")]

    def find(self, name: str) -> Path | None:
        """Resolve a friendly app name to a launchable path, or None."""
        key = name.lower().strip()
        index = self.index

        # exact / alias match against shortcut stems
        for alias in KNOWN_ALIASES.get(key, [key]):
            for indexed, path in index.items():
                if indexed == alias:
                    return path
        # substring match (e.g. "whatsapp" -> "whatsapp desktop.lnk")
        for stem, path in index.items():
            if key in stem:
                return path
        # fallback: on PATH (e.g. code.cmd)
        from shutil import which

        hit = which(name)
        return Path(hit) if hit else None

    def discover(self) -> list[dict[str, str]]:
        """Return safe application metadata without reading private app data."""
        seen: set[str] = set()
        result = []
        for key, path in self.index.items():
            if "::exec" in key or str(path) in seen:
                continue
            seen.add(str(path))
            result.append({"name": key, "path": str(path)})
        return sorted(result, key=lambda item: item["name"])
