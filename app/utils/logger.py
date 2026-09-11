"""Structured logging with secrets redaction."""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from app.config.settings import settings

_REDACTED = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+|\"api_key\"\s*:\s*\"\S+\")",
    re.IGNORECASE,
)

_SENSITIVE_KEYS = {"api_key", "password", "token", "secret", "authorization"}


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _REDACTED.sub("[REDACTED]", str(record.msg))
        if record.args:
            record.args = tuple(
                "[REDACTED]" if isinstance(a, str) and a.lower().split("=")[0] in _SENSITIVE_KEYS and "=" in a else a
                for a in record.args
            ) if isinstance(record.args, tuple) else record.args
        return True


def get_logger(name: str = "assistant") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.addFilter(RedactingFilter())
    logger.addHandler(console)

    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "assistant.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(RedactingFilter())
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
