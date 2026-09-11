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
    tts_rate: int = int(os.getenv("TTS_RATE", "180"))
    wake_word: str = os.getenv("WAKE_WORD", "hey assistant").lower()

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
