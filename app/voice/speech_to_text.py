"""Speech-to-text using faster-whisper (local, offline)."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class STTError(Exception):
    """Raised when local speech recognition cannot process an utterance."""


class SpeechToText(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str: ...


class WhisperSTT(SpeechToText):
    """Local Whisper via faster-whisper. Model is downloaded on first use."""

    def __init__(self, model_size: str | None = None) -> None:
        self._model_size = model_size or settings.whisper_model
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # deferred heavy import

            log.info("Loading Whisper model '%s'...", self._model_size)
            self._model = WhisperModel(self._model_size, device="auto", compute_type="auto")
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        try:
            model = self._load()
            # Automatic detection keeps English, Urdu, Roman Urdu, and mixed speech intact.
            pcm = np.asarray(audio, dtype=np.float32).reshape(-1)
            segments, _info = model.transcribe(
                pcm,
                language=None,
                task="transcribe",
                beam_size=settings.whisper_beam_size,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": settings.whisper_min_silence_ms},
                no_speech_threshold=settings.whisper_no_speech_threshold,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            log.info("Transcription received")
            return text
        except Exception as exc:
            log.error("STT failed: %s", exc)
            raise STTError("I didn't catch that. Please try again.") from exc


class NullSTT(SpeechToText):
    """Used in tests / non-voice runs: returns pre-set text."""

    def __init__(self, canned: str = "") -> None:
        self.canned = canned

    def transcribe(self, audio: np.ndarray) -> str:  # noqa: ARG002
        return self.canned
