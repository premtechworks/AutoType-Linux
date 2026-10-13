"""Logging: rotating file log + console (daemon.log captures console)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from typing import Any

from autotype.paths import get_state_dir

RE_BEARER = re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9_\-\.]{8,}\b")
RE_SK = re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")
RE_SK_ANT = re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b")
RE_NVAPI = re.compile(r"\bnvapi-[A-Za-z0-9_\-]{16,}\b")
RE_GSK = re.compile(r"\bgsk_[A-Za-z0-9_\-]{16,}\b")
RE_HEX_KEY = re.compile(r"\b[0-9a-fA-F]{40}\b")
RE_KEY_ASSIGN = re.compile(
    r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?"
)
RE_TRANSCRIPT = re.compile(
    r"(?m)^(?P<prefix>.*?\b(?:RAW|FINAL|NORMALIZED|PARTIAL):\s*)(?P<content>[^\r\n]+)"
)


def redact_secrets(text: str) -> str:
    """Redact API keys, bearer tokens, and auth secrets from log text."""
    text = RE_BEARER.sub(r"\1 [REDACTED]", text)
    text = RE_SK.sub("[REDACTED]", text)
    text = RE_SK_ANT.sub("[REDACTED]", text)
    text = RE_NVAPI.sub("[REDACTED]", text)
    text = RE_GSK.sub("[REDACTED]", text)
    text = RE_HEX_KEY.sub("[REDACTED]", text)
    text = RE_KEY_ASSIGN.sub(r"\1: [REDACTED]", text)
    return text


def redact_transcripts(text: str) -> str:
    """Redact spoken transcript lines (RAW, FINAL, NORMALIZED, PARTIAL)."""
    return RE_TRANSCRIPT.sub(r"\g<prefix>[REDACTED]", text)


def should_redact_transcripts(levelno: int) -> bool:
    """Transcripts appear only at DEBUG and only if debug recordings/history option is enabled."""
    if levelno > logging.DEBUG:
        return True
    try:
        from autotype import config as cfg
        if cfg.save_recordings():
            return False
        return True
    except Exception:
        return True


class RedactingFormatter(logging.Formatter):
    """Logging formatter for the file handler that redacts secrets and transcripts."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        formatted = redact_secrets(formatted)
        if should_redact_transcripts(record.levelno):
            formatted = redact_transcripts(formatted)
        return formatted


def setup_logging(log_dir: Path | None = None, debug: bool = False) -> logging.Logger:
    """Configure rotating file logger at $XDG_STATE_HOME/autotype/autotype.log and console stream.

    Rotating at 1 MB with 3 backups.
    Default level INFO. Debug flag sets level DEBUG.
    """
    target_dir = Path(log_dir) if log_dir is not None else get_state_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "autotype.log"

    logger = logging.getLogger("autotype")
    log_level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(log_level)

    # If handlers already exist, update their levels and return
    if logger.handlers:
        for handler in logger.handlers:
            handler.setLevel(log_level)
        return logger

    fmt_str = "%(asctime)s %(levelname)s %(message)s"
    date_fmt = "%H:%M:%S"

    # Console handler: unchanged standard formatter
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt_str, datefmt=date_fmt))
    console.setLevel(log_level)

    # File handler: 1 MB rotation (1,000,000 bytes) with 3 backups and redacting formatter
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(RedactingFormatter(fmt_str, datefmt=date_fmt))
    file_handler.setLevel(log_level)

    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger
