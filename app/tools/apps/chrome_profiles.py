"""Safe Chromium profile discovery and selection for Linux."""
from __future__ import annotations
import json, os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
@dataclass(frozen=True)
class ChromeProfile:
    name: str
    directory: str
    user_data_dir: str
    profile_id: str
    last_used: bool = False
    profile_type: str = "local"
    def as_dict(self) -> dict[str, Any]: return asdict(self)
class ChromeProfileManager:
    BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
    def __init__(self, home: Path | None = None) -> None:
        self.home = home or Path.home()
    def user_data_dirs(self) -> list[Path]:
        candidates = [self.home / ".config/google-chrome", self.home / ".config/chromium", self.home / ".config/google-chrome-unstable"]
        return [p for p in candidates if p.is_dir()]
    def discover(self) -> list[ChromeProfile]:
        found: list[ChromeProfile] = []
        for root in self.user_data_dirs():
            state = self._json(root / "Local State")
            info = state.get("profile", {}) if isinstance(state, dict) else {}
            last = str(state.get("profile", {}).get("last_used", "")) if isinstance(state.get("profile"), dict) else ""
            for child in sorted(root.iterdir()):
                if not child.is_dir() or not (child.name == "Default" or child.name.startswith("Profile ")): continue
                prefs = self._json(child / "Preferences")
                cache = prefs.get("profile", {}) if isinstance(prefs, dict) else {}
                name = str(info.get("info_cache", {}).get(child.name, {}).get("name", "")) or str(cache.get("name", "")) or ("Personal" if child.name == "Default" else child.name)
                found.append(ChromeProfile(name=name, directory=child.name, user_data_dir=str(root), profile_id=child.name, last_used=child.name == last, profile_type=str(cache.get("profile_type", "local"))))
        return found
    def select(self, requested: str) -> list[ChromeProfile]:
        key = requested.lower().strip()
        profiles = self.discover()
        exact = [p for p in profiles if p.name.lower() == key or p.directory.lower() == key or p.profile_id.lower() == key]
        if exact: return exact
        return [p for p in profiles if key in p.name.lower() or key in p.directory.lower()]
    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        try: return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return {}
