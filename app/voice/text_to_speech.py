"""Text-to-speech via pyttsx3 (SAPI5 on Windows, fully offline)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)



class TTS(ABC):
    @abstractmethod
    def speak(self, text: str) -> None: ...


class Pyttsx3TTS(TTS):
    def __init__(self, rate: int | None = None) -> None:
        self.rate = rate or settings.tts_rate
        self._engine = None

    def _load(self):
        if self._engine is None:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
        return self._engine

    def speak(self, text: str) -> None:
        if not text:
            return
        try:
            engine = self._load()
            engine.say(text)
            engine.runAndWait()
            log.info("TTS spoken: %r", text)
        except Exception as exc:
            log.error("TTS failed (continuing silently): %s", exc)


class PrintTTS(TTS):
    """Fallback that prints instead of speaking (CI, tests, headless runs)."""

    def speak(self, text: str) -> None:
        if text:
            print(f"Assistant: {text}")
