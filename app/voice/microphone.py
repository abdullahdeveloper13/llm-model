"""Microphone capture with adaptive energy VAD and pre-roll."""
from __future__ import annotations

import queue
from collections import deque

import numpy as np
import sounddevice as sd

from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)
SAMPLE_RATE = settings.sample_rate
FRAME_MS = settings.frame_ms
PRE_ROLL_MS = settings.pre_roll_ms
SILENCE_LIMIT_MS = settings.silence_limit_ms
MAX_RECORD_MS = settings.max_record_ms
MIN_SPEECH_MS = settings.min_speech_ms


class MicrophoneError(Exception):
    """Raised when the microphone cannot be accessed."""


class Microphone:
    """Blocking recorder: wait for speech, then stop after trailing silence."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, frame_ms: int = FRAME_MS,
                 pre_roll_ms: int = PRE_ROLL_MS, silence_limit_ms: int = SILENCE_LIMIT_MS,
                 max_record_ms: int = MAX_RECORD_MS, min_speech_ms: int = MIN_SPEECH_MS,
                 energy_threshold: float = settings.vad_threshold,
                 noise_multiplier: float = settings.vad_noise_multiplier,
                 device: str | int | None = None,
                 queue_timeout: float = settings.microphone_queue_timeout,
                 max_queue_timeouts: int = settings.microphone_max_queue_timeouts) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.pre_roll_ms = pre_roll_ms
        self.silence_limit_ms = silence_limit_ms
        self.max_record_ms = max_record_ms
        self.min_speech_ms = min_speech_ms
        self.energy_threshold = energy_threshold
        self.noise_multiplier = noise_multiplier
        self.device = device or settings.microphone_device or None
        self.queue_timeout = queue_timeout
        self.max_queue_timeouts = max_queue_timeouts
        self._queue: queue.Queue[np.ndarray] = queue.Queue()

    def list_devices(self) -> list[str]:
        try:
            return [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        except Exception as exc:  # pragma: no cover - hardware specific
            raise MicrophoneError(f"Cannot query audio devices: {exc}") from exc

    def record(self) -> np.ndarray:
        """Return one utterance as float32 mono PCM, or empty audio for no speech."""
        try:
            stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="float32",
                                    blocksize=int(self.sample_rate * self.frame_ms / 1000),
                                    callback=self._callback, device=self.device)
        except Exception as exc:
            raise MicrophoneError(f"Can't access the microphone: {exc}") from exc

        frames: list[np.ndarray] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=max(1, self.pre_roll_ms // self.frame_ms))
        elapsed_ms = silence_ms = speech_ms = 0
        empty_timeouts = 0
        spoken = False
        noise_floor: float | None = None
        calibration_frames = max(3, round(300 / self.frame_ms))
        observed_frames = 0
        try:
            with stream:
                log.info("Microphone: listening...")
                while elapsed_ms < self.max_record_ms:
                    try:
                        frame = self._queue.get(timeout=self.queue_timeout)
                    except queue.Empty:
                        empty_timeouts += 1
                        if spoken:
                            break
                        if empty_timeouts >= self.max_queue_timeouts:
                            break
                        continue
                    empty_timeouts = 0
                    observed_frames += 1
                    elapsed_ms = observed_frames * self.frame_ms
                    frame = np.asarray(frame, dtype=np.float32).reshape(-1)
                    energy = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
                    threshold = max(self.energy_threshold, (noise_floor or 0.0) * self.noise_multiplier)
                    is_speech = observed_frames > calibration_frames and energy > threshold
                    if not spoken and observed_frames <= calibration_frames:
                        is_speech = False
                    if not spoken and not is_speech:
                        noise_floor = energy if noise_floor is None else 0.92 * noise_floor + 0.08 * energy
                    if is_speech:
                        if not spoken:
                            frames.extend(pre_roll)
                            pre_roll.clear()
                        spoken = True
                        speech_ms += self.frame_ms
                        silence_ms = 0
                        frames.append(frame)
                    elif spoken:
                        silence_ms += self.frame_ms
                        frames.append(frame)
                        if silence_ms >= self.silence_limit_ms:
                            break
                    else:
                        pre_roll.append(frame)
        except (OSError, sd.PortAudioError) as exc:
            raise MicrophoneError(f"Microphone stream failed: {exc}") from exc
        finally:
            self._clear_queue()
        if not spoken or speech_ms < self.min_speech_ms:
            log.info("Microphone: no speech detected")
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(frames).astype(np.float32, copy=False).flatten()
        log.info("Microphone: captured %.1fs of audio", len(audio) / self.sample_rate)
        return audio

    def _clear_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _callback(self, indata, _frames, _time, status) -> None:
        if status:
            log.debug("Microphone callback status: %s", status)
        self._queue.put(indata.copy())
