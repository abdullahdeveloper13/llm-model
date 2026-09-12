"""Application configuration loaded from environment variables (.env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """Central, typed access to all configuration."""

    # --- LLM ---
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # --- API server ---
    agent_host: str = os.getenv("AGENT_HOST", "127.0.0.1")
    agent_port: int = int(os.getenv("AGENT_PORT", "8000"))

    # --- Behaviour ---
    mode: str = os.getenv("ASSISTANT_MODE", "development").lower()  # dev|production
    confirmation_timeout: int = int(os.getenv("CONFIRMATION_TIMEOUT", "60"))
    app_shortcuts_path: str = os.getenv("APP_SHORTCUTS_PATH", "")

    # --- Voice ---
    whisper_model: str = os.getenv("WHISPER_MODEL", "base")
    whisper_beam_size: int = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
    whisper_min_silence_ms: int = int(os.getenv("WHISPER_MIN_SILENCE_MS", "500"))
    whisper_no_speech_threshold: float = float(os.getenv("WHISPER_NO_SPEECH_THRESHOLD", "0.6"))
    tts_rate: int = int(os.getenv("TTS_RATE", "180"))
    wake_word: str = os.getenv("WAKE_WORD", "hey assistant").lower()
    sample_rate: int = int(os.getenv("SAMPLE_RATE", "16000"))
    frame_ms: int = int(os.getenv("FRAME_MS", "30"))
    pre_roll_ms: int = int(os.getenv("PRE_ROLL_MS", "300"))
    silence_limit_ms: int = int(os.getenv("SILENCE_LIMIT_MS", "750"))
    max_record_ms: int = int(os.getenv("MAX_RECORD_MS", "15000"))
    min_speech_ms: int = int(os.getenv("MIN_SPEECH_MS", "240"))
    vad_threshold: float = float(os.getenv("VAD_THRESHOLD", "0.010"))
    vad_noise_multiplier: float = float(os.getenv("VAD_NOISE_MULTIPLIER", "3.0"))
    microphone_device: str = os.getenv("MICROPHONE_DEVICE", "")
    microphone_queue_timeout: float = float(os.getenv("MICROPHONE_QUEUE_TIMEOUT", "2.0"))
    microphone_max_queue_timeouts: int = int(os.getenv("MICROPHONE_MAX_QUEUE_TIMEOUTS", "3"))

    # --- Storage ---
    data_dir: Path = PROJECT_ROOT / "data"
    db_path: Path = data_dir / "assistant.db"

    @property
    def is_production(self) -> bool:
        return self.mode == "production"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
