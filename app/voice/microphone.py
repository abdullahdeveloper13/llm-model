"""Microphone capture. Records a single utterance with VAD-style silence trim."""
from __future__ import annotations

import queue

import numpy as np
import sounddevice as sd

from app.utils.logger import get_logger

log = get_logger(__name__)

SAMPLE_RATE = 16_000
FRAME_MS = 30
SILENCE_LIMIT_MS = 900
MAX_RECORD_MS = 12_000


class MicrophoneError(Exception):
    """Raised when the microphone cannot be accessed."""


class Microphone:
    """Blocking recorder: wait for speech, record, stop after trailing silence."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        silence_limit_ms: int = SILENCE_LIMIT_MS,
        max_record_ms: int = MAX_RECORD_MS,
        energy_threshold: float = 0.010,
    ) -> None:
        self.sample_rate = sample_rate
        self.silence_limit_ms = silence_limit_ms
        self.max_record_ms = max_record_ms
        self.energy_threshold = energy_threshold
        self._queue: queue.Queue[np.ndarray] = queue.Queue()

    def list_devices(self) -> list[str]:
        try:
            return [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        except Exception as exc:  # pragma: no cover - hardware specific
            raise MicrophoneError(f"Cannot query audio devices: {exc}") from exc

    def record(self) -> np.ndarray:
        """Record until trailing silence or max duration. Returns float32 mono PCM."""
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=int(self.sample_rate * FRAME_MS / 1000),
                callback=self._callback,
            )
        except Exception as exc:
            raise MicrophoneError(f"Can't access the microphone: {exc}") from exc

        frames: list[np.ndarray] = []
        silence_ms = 0
        spoken = False
        try:
            with stream:
                log.info("Microphone: listening...")
                while len(frames) * FRAME_MS < self.max_record_ms:
                    frame = self._queue.get(timeout=5)
                    energy = float(np.sqrt(np.mean(frame ** 2)))
                    if energy > self.energy_threshold:
                        spoken = True
                        silence_ms = 0
                    elif spoken:
                        silence_ms += FRAME_MS
                        if silence_ms >= self.silence_limit_ms:
                            break
                    frames.append(frame)
        finally:
            with self._queue.mutex:
                self._queue.queue.clear()

        if not spoken:
            log.info("Microphone: no speech detected")
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(frames).flatten()
        log.info("Microphone: captured %.1fs of audio", len(audio) / self.sample_rate)
        return audio

    def _callback(self, indata, _frames, _time, _status) -> None:
        self._queue.put(indata.copy())
