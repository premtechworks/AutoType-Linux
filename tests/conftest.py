"""Shared test fixtures for AutoType unit tests."""
import os
from pathlib import Path
import pytest

AUTOTYPE_ENV_VARS = [
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "PROCESSING_MODE",
    "COMMAND_PREFIX",
    "SAVE_RECORDINGS",
    "USE_CUSTOM_PROMPT",
    "CUSTOM_PROMPT_FILE",
    "MIC_DEVICE",
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "CLEANING_TEMPERATURE",
    "OMNIROUTE_BASE_URL",
    "OMNIROUTE_API_KEY",
    "OMNIROUTE_MODEL",
    "STT_BACKEND",
    "CLOUD_STT_PROVIDER",
    "CLOUD_STT_API_KEY",
    "CLOUD_STT_BASE_URL",
    "CLOUD_STT_MODEL",
    "CLOUD_STT_LANGUAGE",
    "DEEPGRAM_API_KEY",
    "DEEPGRAM_MODEL",
    "DEEPGRAM_LANGUAGE",
    "DEEPGRAM_FLUX_MODEL",
    "PARAKEET_BINARY",
    "PARAKEET_MODEL",
    "PARAKEET_STREAM_BINARY",
    "PARAKEET_STREAM_MODEL",
]


@pytest.fixture
def clean_autotype_env(monkeypatch):
    """Ensure environment is clean of AutoType settings."""
    for var in AUTOTYPE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def isolated_xdg(tmp_path, monkeypatch, clean_autotype_env):
    """Provide isolated XDG_CONFIG_HOME, XDG_DATA_HOME, and XDG_STATE_HOME paths."""
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    state_home = tmp_path / "state"
    config_home.mkdir(parents=True, exist_ok=True)
    data_home.mkdir(parents=True, exist_ok=True)
    state_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))

    # Reset logged state in paths
    import autotype.paths
    autotype.paths._logged_data_mode = False
    monkeypatch.setattr(autotype.paths, "find_repo_root", lambda: None)

    return {
        "config_home": config_home,
        "data_home": data_home,
        "state_home": state_home,
        "config_dir": config_home / "autotype",
        "data_dir": data_home / "autotype",
        "state_dir": state_home / "autotype",
        "config_file": config_home / "autotype" / "config.toml",
        "log_file": state_home / "autotype" / "autotype.log",
    }
