"""Unit tests verifying configuration precedence: Environment Variable > config.toml > Defaults."""
import pytest

from autotype import config


def test_env_var_overrides_toml(isolated_xdg, monkeypatch):
    # Set config.toml
    config.save_config({
        "general": {
            "processing_mode": "email",
            "command_prefix": "computer",
            "save_recordings": False,
        },
        "llm": {
            "provider": "openai",
            "api_key": "toml-key",
            "temperature": 0.2,
        },
        "stt": {
            "backend": "deepgram",
        },
    })

    # Initially matches TOML
    assert config.processing_mode() == "email"
    assert config.llm_api_key() == "toml-key"
    assert config.cleaning_temperature() == 0.2
    assert config.stt_backend() == "deepgram"

    # Set environment variables to override
    monkeypatch.setenv("PROCESSING_MODE", "code")
    monkeypatch.setenv("LLM_API_KEY", "env-key-override")
    monkeypatch.setenv("CLEANING_TEMPERATURE", "0.7")
    monkeypatch.setenv("STT_BACKEND", "whisper")

    assert config.processing_mode() == "code"
    assert config.llm_api_key() == "env-key-override"
    assert config.cleaning_temperature() == 0.7
    assert config.stt_backend() == "whisper"


def test_toml_overrides_defaults(isolated_xdg):
    # No env vars set; verify TOML overrides default
    config.save_config({
        "general": {
            "processing_mode": "casual",
            "command_prefix": "robot",
        },
        "llm": {
            "provider": "anthropic",
        },
    })

    assert config.processing_mode() == "casual"
    assert config.command_prefix() == "robot"
    assert config.llm_provider() == "anthropic"


def test_legacy_omniroute_env_fallback(isolated_xdg, monkeypatch):
    monkeypatch.setenv("OMNIROUTE_BASE_URL", "https://omni.example.com/v1")
    monkeypatch.setenv("OMNIROUTE_API_KEY", "omni-secret-key")
    monkeypatch.setenv("OMNIROUTE_MODEL", "omni-pro")

    assert config.llm_provider() == "custom"
    assert config.llm_base_url() == "https://omni.example.com/v1"
    assert config.llm_api_key() == "omni-secret-key"
    assert config.llm_model() == "omni-pro"


def test_empty_env_var_falls_back_to_toml(isolated_xdg, monkeypatch):
    config.save_config({
        "llm": {
            "provider": "groq",
            "api_key": "groq-key-from-toml",
        },
    })
    # Blank env var should not wipe out TOML value
    monkeypatch.setenv("LLM_API_KEY", "   ")
    assert config.llm_api_key() == "groq-key-from-toml"
