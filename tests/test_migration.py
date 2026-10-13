"""Unit tests for automatic first-run migration from .env and gui_settings.json."""
import json
import logging
import os
from pathlib import Path
import stat
import pytest

from autotype import migration
from autotype.toml_io import load_toml


def test_first_run_migration_from_env_and_gui(tmp_path, caplog):
    # Prepare legacy files in temporary directories
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()

    env_path = legacy_dir / ".env"
    env_content = (
        "LLM_PROVIDER=anthropic\n"
        "LLM_API_KEY=sk-ant-secret123456\n"
        "LLM_MODEL=claude-3-5-haiku-20241022\n"
        "CLEANING_TEMPERATURE=0.25\n"
        "STT_BACKEND=deepgram\n"
        "DEEPGRAM_API_KEY=dg-secret987654\n"
        "PROCESSING_MODE=code\n"
        "COMMAND_PREFIX=jarvis\n"
        "SAVE_RECORDINGS=true\n"
    )
    env_path.write_text(env_content, encoding="utf-8")

    gui_path = legacy_dir / "gui_settings.json"
    gui_data = {
        "active_stt": "Fast STT",
        "active_clean": "Smart Code",
        "stt_profiles": {
            "Fast STT": {"STT_BACKEND": "deepgram", "DEEPGRAM_MODEL": "nova-3"},
        },
        "clean_profiles": {
            "Smart Code": {"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-3-5-haiku-20241022"},
        },
    }
    gui_path.write_text(json.dumps(gui_data), encoding="utf-8")

    dest_config = tmp_path / "autotype" / "config.toml"

    with caplog.at_level(logging.INFO):
        migrated = migration.migrate_if_needed(
            config_path=dest_config,
            legacy_env_path=env_path,
            legacy_gui_path=gui_path,
        )

    assert migrated is True
    assert dest_config.is_file()

    # Verify chmod 0600
    file_mode = stat.S_IMODE(os.stat(dest_config).st_mode)
    assert file_mode == 0o600

    # Verify originals remain untouched
    assert env_path.is_file()
    assert env_path.read_text(encoding="utf-8") == env_content
    assert gui_path.is_file()
    assert json.loads(gui_path.read_text(encoding="utf-8")) == gui_data

    # Verify content in config.toml
    parsed = load_toml(dest_config.read_text(encoding="utf-8"))
    assert parsed["general"]["processing_mode"] == "code"
    assert parsed["general"]["command_prefix"] == "jarvis"
    assert parsed["general"]["save_recordings"] is True

    assert parsed["llm"]["provider"] == "anthropic"
    assert parsed["llm"]["api_key"] == "sk-ant-secret123456"
    assert parsed["llm"]["model"] == "claude-3-5-haiku-20241022"
    assert parsed["llm"]["temperature"] == 0.25

    assert parsed["stt"]["backend"] == "deepgram"
    assert parsed["stt"]["deepgram_api_key"] == "dg-secret987654"

    assert parsed["profiles"]["active_stt"] == "Fast STT"
    assert parsed["profiles"]["active_clean"] == "Smart Code"
    assert "Fast STT" in parsed["profiles"]["stt"]
    assert "Smart Code" in parsed["profiles"]["clean"]

    # Verify secrets were never logged
    assert "sk-ant-secret123456" not in caplog.text
    assert "dg-secret987654" not in caplog.text
    # But setting names were logged
    assert "LLM_API_KEY" in caplog.text
    assert "DEEPGRAM_API_KEY" in caplog.text


def test_migration_noop_when_config_exists(tmp_path):
    dest_config = tmp_path / "config.toml"
    dest_config.write_text('[general]\nprocessing_mode = "raw"\n', encoding="utf-8")

    env_path = tmp_path / ".env"
    env_path.write_text("PROCESSING_MODE=clean\n", encoding="utf-8")

    migrated = migration.migrate_if_needed(
        config_path=dest_config,
        legacy_env_path=env_path,
        legacy_gui_path=None,
    )

    assert migrated is False
    # File kept original contents
    assert 'processing_mode = "raw"' in dest_config.read_text(encoding="utf-8")
