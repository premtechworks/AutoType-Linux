"""Unit tests for configuration reading, defaults, types, and serialization."""
import os
from pathlib import Path
import stat
import pytest

from autotype import config
from autotype.toml_io import dump_toml, load_toml


def test_toml_roundtrip():
    data = {
        "general": {
            "processing_mode": "code",
            "save_recordings": True,
            "count": 42,
            "ratio": 3.14,
        },
        "llm": {
            "provider": "anthropic",
            "model": "claude-3-5-haiku-20241022",
        },
    }
    encoded = dump_toml(data)
    decoded = load_toml(encoded)
    assert decoded["general"]["processing_mode"] == "code"
    assert decoded["general"]["save_recordings"] is True
    assert decoded["general"]["count"] == 42
    assert decoded["general"]["ratio"] == 3.14
    assert decoded["llm"]["provider"] == "anthropic"


def test_config_defaults(isolated_xdg):
    # Isolated XDG with no config.toml and clean environment
    assert config.llm_provider() == "openai"
    assert config.llm_base_url() == "https://api.openai.com/v1"
    assert config.llm_model() == "gpt-4o-mini"
    assert config.cleaning_temperature() == 0.1
    assert config.stt_backend() == "deepgram"
    assert config.deepgram_model() == "nova-3"
    assert config.deepgram_language() == "en-US"
    assert config.deepgram_flux_model() == "flux-general-en"
    assert config.cloud_stt_provider() == "deepgram"
    assert config.cloud_stt_model() == "whisper-1"
    assert config.processing_mode() == "clean"
    assert config.command_prefix() == "computer"
    assert config.save_recordings() is False
    assert config.use_custom_prompt() is False
    assert config.mic_device() == ""


def test_load_and_save_config(isolated_xdg):
    cfg_file = isolated_xdg["config_file"]
    data = {
        "general": {
            "processing_mode": "smart",
            "command_prefix": "jarvis",
            "save_recordings": True,
        },
        "llm": {
            "provider": "groq",
            "api_key": "gsk_test123",
            "temperature": 0.3,
        },
    }
    config.save_config(data)

    assert cfg_file.is_file()
    # Check permissions 0600
    file_mode = stat.S_IMODE(os.stat(cfg_file).st_mode)
    assert file_mode == 0o600

    loaded = config.load_config()
    assert loaded["general"]["processing_mode"] == "smart"
    assert loaded["general"]["command_prefix"] == "jarvis"
    assert loaded["general"]["save_recordings"] is True
    assert loaded["llm"]["provider"] == "groq"
    assert loaded["llm"]["api_key"] == "gsk_test123"

    # Verify getters read config.toml
    assert config.processing_mode() == "smart"
    assert config.command_prefix() == "jarvis"
    assert config.save_recordings() is True
    assert config.llm_provider() == "groq"
    assert config.llm_api_key() == "gsk_test123"
    assert config.cleaning_temperature() == 0.3


def test_backward_compat_shim():
    import config as root_config

    assert hasattr(root_config, "load_config")
    assert hasattr(root_config, "save_config")
    assert hasattr(root_config, "llm_provider")
    assert hasattr(root_config, "stt_backend")
    assert hasattr(root_config, "omniroute_base_url")
    assert hasattr(root_config, "omniroute_api_key")
    assert hasattr(root_config, "omniroute_model")


def test_local_stt_path_auto_resolution(isolated_xdg, tmp_path, monkeypatch):
    # Setup mock XDG data bin and models directories
    share_dir = tmp_path / "custom_data"
    bin_dir = share_dir / "autotype" / "bin"
    models_dir = share_dir / "autotype" / "models"
    bin_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)

    fake_cli = bin_dir / "parakeet-cli"
    fake_cli.write_bytes(b"\x7fELF")
    os.chmod(fake_cli, 0o755)

    fake_model = models_dir / "parakeet-eou-120m-q8_0.gguf"
    fake_model.write_bytes(b"GGUF")

    monkeypatch.setattr("autotype.paths.get_bin_dir", lambda: bin_dir)
    monkeypatch.setattr("autotype.paths.get_models_dir", lambda: models_dir)

    # 1. No env and no config.toml -> auto-resolves to installed XDG paths
    assert config.parakeet_stream_binary() == str(fake_cli)
    assert config.parakeet_stream_model() == str(fake_model)

    # 2. Explicit config.toml overrides auto-resolution
    config.save_config({
        "stt": {
            "parakeet_stream_binary": "/opt/custom/parakeet-cli",
            "parakeet_stream_model": "/opt/custom/model.gguf",
        }
    })
    assert config.parakeet_stream_binary() == "/opt/custom/parakeet-cli"
    assert config.parakeet_stream_model() == "/opt/custom/model.gguf"

    # 3. Environment variable overrides config.toml
    monkeypatch.setenv("PARAKEET_STREAM_BINARY", "/env/override/parakeet-cli")
    monkeypatch.setenv("PARAKEET_STREAM_MODEL", "/env/override/model.gguf")
    assert config.parakeet_stream_binary() == "/env/override/parakeet-cli"
    assert config.parakeet_stream_model() == "/env/override/model.gguf"


def test_first_run_completed_setting(isolated_xdg):
    assert config.first_run_completed() is False
    config.set_first_run_completed(True)
    assert config.first_run_completed() is True

