"""Wake-word detection hook.

The architecture keeps wake-word detection optional: the core loop works in
push-to-talk / always-listen mode without it. When optional dependencies
(porcupine / openWakeWord) are installed, `WakeWordDetector` can gate the
main loop. Detection itself can also run by checking each transcript for
the configured wake phrase — zero extra dependencies, reasonable accuracy.
"""
from __future__ import annotations

from app.config.settings import settings


class WakeWordDetector:
    """Checks a transcript for the configured wake phrase."""

    def __init__(self, phrase: str | None = None, enabled: bool = False) -> None:
        self.phrase = (phrase or settings.wake_word).lower()
        self.enabled = enabled

    def contains(self, text: str) -> bool:
        return self.phrase in text.lower()

    def strip(self, text: str) -> str:
        """Remove the wake phrase from the transcript."""
        return text.lower().replace(self.phrase, "").strip(" ,.!") or text


def should_activate(detector: WakeWordDetector, text: str, require_wake: bool) -> bool:
    """Decide if a transcript should trigger the assistant."""
    if not require_wake:
        return True
    return detector.contains(text)
