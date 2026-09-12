"""Assistant: full voice loop wiring microphone -> STT -> orchestrator -> TTS."""
from __future__ import annotations

import numpy as np
import time

from app.config.settings import settings
from app.core.orchestrator import Orchestrator
from app.utils.logger import get_logger
from app.voice.microphone import Microphone, MicrophoneError
from app.voice.speech_to_text import SpeechToText, STTError, WhisperSTT
from app.voice.text_to_speech import Pyttsx3TTS, TTS
from app.voice.wake_word import WakeWordDetector

log = get_logger(__name__)


class Assistant:
    """Reusable core used by both the CLI loop and the API server."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        stt: SpeechToText | None = None,
        tts: TTS | None = None,
        mic: Microphone | None = None,
        require_wake_word: bool = False,
    ) -> None:
        self.orchestrator = orchestrator
        self.mic = mic or Microphone()
        self.stt = stt or WhisperSTT()
        self.tts = tts or Pyttsx3TTS()
        self.wake = WakeWordDetector(enabled=require_wake_word)
        self.running = False
        self.retry_delay = 1.0

    # -- one full voice round: returns what was heard & answered ------------
    def listen_once(self) -> tuple[str, str]:
        try:
            audio = self.mic.record()
        except MicrophoneError as exc:
            self._speak("I can't access the microphone.")
            log.warning("Microphone unavailable; retrying: %s", exc)
            time.sleep(self.retry_delay)
            return "", str(exc)
        try:
            text = self.stt.transcribe(audio)
        except STTError:
            self._speak("I didn't catch that. Please try again.")
            time.sleep(0.2)
            return "", ""
        if not text:
            return "", ""
        log.info("User transcript received")
        if not self._should_handle(text):
            return text, ""
        result = self.orchestrator.handle(text)
        log.info("Assistant: %s", result.response)
        self._speak(result.response)
        return text, result.response

    def run(self) -> None:
        """Continuous loop. Ctrl+C to stop."""
        self.running = True
        self._speak("Assistant started. I'm listening.")
        try:
            while self.running:
                try:
                    self.listen_once()
                except Exception:
                    log.exception("Voice round failed; continuing to listen")
                    time.sleep(self.retry_delay)
        except KeyboardInterrupt:
            log.info("Assistant stopped by user")
        finally:
            self.running = False
            self.orchestrator.reset_session()

    def stop(self) -> None:
        self.running = False

    # -- helpers -------------------------------------------------------------
    def _should_handle(self, text: str) -> bool:
        if not self.wake.enabled:
            return True
        if not self.wake.contains(text):
            return False
        stripped = self.wake.strip(text)
        if stripped and stripped != text:
            log.info("Wake word detected; command: %r", stripped)
        return True

    def _speak(self, text: str) -> None:
        if text:
            self.tts.speak(text)


def text_only_assistant() -> Assistant:
    """Assistant that skips STT/TTS entirely (used for CLI text mode / tests)."""
    orch = Orchestrator()
    return Assistant(orch, stt=_NullSTT(), tts=_NullTTS())


class _NullSTT(SpeechToText):
    def transcribe(self, audio: np.ndarray) -> str:  # noqa: ARG002
        return ""


class _NullTTS(TTS):
    def speak(self, text: str) -> None:
        if text:
            print(f"Assistant: {text}")
