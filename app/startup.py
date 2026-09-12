"""User-level Windows Startup-folder installation."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def startup_command_path() -> Path:
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "JarvisAssistant.cmd"


def install_startup() -> Path:
    target = startup_command_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    project = Path(__file__).resolve().parents[1]
    python = Path(sys.executable)
    run_path = project / "run.py"
    target.write_text(
        f'@echo off\nstart "Jarvis Assistant" /min "{python}" "{run_path}" --voice\n',
        encoding="utf-8",
    )
    return target


def remove_startup() -> bool:
    target = startup_command_path()
    if target.exists():
        target.unlink()
        return True
    return False
