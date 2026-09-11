"""Security helpers: subprocess whitelisting and output limits."""
from __future__ import annotations

import subprocess

from app.utils.logger import get_logger

log = get_logger(__name__)

# The ONLY external executables tools may ever invoke. Nothing coming from
# the LLM can extend this list; it is changed only via code review.
ALLOWED_BINARIES = {
    "shutdown.exe": r"C:\Windows\System32\shutdown.exe",
    "tasklist.exe": r"C:\Windows\System32\tasklist.exe",
}


def run_allowed(binary: str, args: list[str], timeout: float = 20) -> str:
    """Run a whitelisted system binary. Raises ValueError for anything else."""
    key = binary.lower()
    if key not in ALLOWED_BINARIES:
        raise ValueError(f"Binary '{binary}' is not in the allow-list")
    cmd = [ALLOWED_BINARIES[key], *args]
    log.info("Running allowed binary: %s", " ".join(cmd))
    result = subprocess.run(  # noqa: S603 - binary comes from ALLOWED_BINARIES only
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )
    return (result.stdout or result.stderr or "").strip()


def clip(text: str, limit: int = 4000) -> str:
    """Truncate long tool output before it reaches logs or the LLM."""
    return text if len(text) <= limit else text[: limit - 3] + "..."
