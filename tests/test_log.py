"""Unit tests for rotating file logging, secret redaction, and transcript redaction."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import pytest

from autotype import paths
from utils import log as autotype_log


def test_redact_secrets():
    text = (
        "Connected with Authorization: Bearer secret-bearer-token-123456\n"
        "Deepgram token: Token 1234567890abcdef1234567890abcdef12345678\n"
        "OpenAI key sk-abcdef1234567890abcdef1234567890 and Anthropic sk-ant-api03-abcdef1234567890abcdef1234567890\n"
        "NVIDIA nvapi-abcdef1234567890abcdef and Groq gsk_abcdef1234567890abcdef\n"
        "Assignment api_key='supersecretvalue123'"
    )
    redacted = autotype_log.redact_secrets(text)
    assert "secret-bearer-token" not in redacted
    assert "Bearer [REDACTED]" in redacted
    assert "Token [REDACTED]" in redacted
    assert "sk-abcdef" not in redacted
    assert "sk-ant-" not in redacted
    assert "nvapi-" not in redacted
    assert "gsk_" not in redacted
    assert "supersecretvalue" not in redacted
    assert "[REDACTED]" in redacted


def test_transcript_redaction_at_info_level(tmp_path, isolated_xdg):
    logger = logging.getLogger("autotype.test_info")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    log_file = tmp_path / "autotype.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(autotype_log.RedactingFormatter("%(message)s"))
    logger.addHandler(file_handler)

    logger.info("RAW: this is private speech text")
    logger.info("NORMALIZED: this is normalized private text")
    logger.info("FINAL: final inserted text")
    logger.info("Timing: record=1.0s stt=0.5s")
    file_handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "this is private speech text" not in content
    assert "this is normalized private text" not in content
    assert "final inserted text" not in content
    assert "RAW: [REDACTED]" in content
    assert "NORMALIZED: [REDACTED]" in content
    assert "FINAL: [REDACTED]" in content
    assert "Timing: record=1.0s stt=0.5s" in content


def test_transcript_redaction_at_debug_without_save_recordings(tmp_path, monkeypatch, isolated_xdg):
    monkeypatch.setenv("SAVE_RECORDINGS", "false")

    logger = logging.getLogger("autotype.test_debug_no_save")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    log_file = tmp_path / "autotype.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(autotype_log.RedactingFormatter("%(message)s"))
    logger.addHandler(file_handler)

    logger.debug("RAW: secret speech in debug mode")
    file_handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "secret speech in debug mode" not in content
    assert "RAW: [REDACTED]" in content


def test_transcript_unredacted_at_debug_with_save_recordings(tmp_path, monkeypatch, isolated_xdg):
    monkeypatch.setenv("SAVE_RECORDINGS", "true")

    logger = logging.getLogger("autotype.test_debug_save")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    log_file = tmp_path / "autotype.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(autotype_log.RedactingFormatter("%(message)s"))
    logger.addHandler(file_handler)

    logger.debug("RAW: debug speech with save_recordings enabled")
    file_handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "debug speech with save_recordings enabled" in content
    assert "RAW: debug speech with save_recordings enabled" in content


def test_setup_logging_rotation_parameters(tmp_path, isolated_xdg):
    logger = logging.getLogger("autotype")
    logger.handlers.clear()

    autotype_log.setup_logging(tmp_path, debug=False)
    assert logger.level == logging.INFO

    file_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    fh = file_handlers[0]
    assert fh.maxBytes == 1_000_000
    assert fh.backupCount == 3
    assert fh.baseFilename == str(tmp_path / "autotype.log")
    assert isinstance(fh.formatter, autotype_log.RedactingFormatter)


def test_console_output_unchanged(capsys, tmp_path, isolated_xdg):
    logger = logging.getLogger("autotype")
    logger.handlers.clear()

    autotype_log.setup_logging(tmp_path, debug=False)
    logger.info("RAW: spoken words here")

    captured = capsys.readouterr()
    # Console output handler should remain unchanged and print unredacted
    assert "RAW: spoken words here" in captured.err

    # But file handler must be redacted
    log_file = tmp_path / "autotype.log"
    content = log_file.read_text(encoding="utf-8")
    assert "spoken words here" not in content
    assert "RAW: [REDACTED]" in content
