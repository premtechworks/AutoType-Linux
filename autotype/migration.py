"""First-run migration from legacy .env and data/gui_settings.json to config.toml."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from autotype.paths import find_repo_root, get_config_path, get_data_dir
from autotype.toml_io import dump_toml

log = logging.getLogger("autotype.migration")

SECRET_KEYWORDS = ("KEY", "SECRET", "PASSWORD", "TOKEN")


def is_secret_key(key: str) -> bool:
    """Return True if the key name indicates a sensitive secret."""
    key_upper = key.upper()
    return any(kw in key_upper for kw in SECRET_KEYWORDS)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into key-value pairs."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                result[k] = v.strip().strip("'\"")
    except Exception as exc:
        log.warning("Could not read .env file at %s: %exc", path, exc)
    return result


def parse_gui_settings(path: Path) -> dict[str, Any]:
    """Parse gui_settings.json into dictionary."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        log.warning("Could not read gui_settings.json at %s: %s", path, exc)
    return {}


def build_migrated_config(env: dict[str, str], gui: dict[str, Any]) -> dict[str, Any]:
    """Combine .env and gui_settings.json into consolidated TOML dictionary structure."""
    cfg: dict[str, Any] = {
        "general": {},
        "llm": {},
        "stt": {},
        "profiles": {},
    }

    # General / Behavior
    if "PROCESSING_MODE" in env:
        cfg["general"]["processing_mode"] = env["PROCESSING_MODE"]
    if "COMMAND_PREFIX" in env:
        cfg["general"]["command_prefix"] = env["COMMAND_PREFIX"]
    if "SAVE_RECORDINGS" in env:
        cfg["general"]["save_recordings"] = env["SAVE_RECORDINGS"].lower() in ("1", "true", "yes")
    if "USE_CUSTOM_PROMPT" in env:
        cfg["general"]["use_custom_prompt"] = env["USE_CUSTOM_PROMPT"].lower() in ("1", "true", "yes")
    if "CUSTOM_PROMPT_FILE" in env:
        cfg["general"]["custom_prompt_file"] = env["CUSTOM_PROMPT_FILE"]
    if "MIC_DEVICE" in env:
        cfg["general"]["mic_device"] = env["MIC_DEVICE"]

    # LLM
    if "LLM_PROVIDER" in env:
        cfg["llm"]["provider"] = env["LLM_PROVIDER"]
    if "LLM_BASE_URL" in env:
        cfg["llm"]["base_url"] = env["LLM_BASE_URL"]
    if "LLM_API_KEY" in env:
        cfg["llm"]["api_key"] = env["LLM_API_KEY"]
    if "LLM_MODEL" in env:
        cfg["llm"]["model"] = env["LLM_MODEL"]
    if "CLEANING_TEMPERATURE" in env:
        try:
            cfg["llm"]["temperature"] = float(env["CLEANING_TEMPERATURE"])
        except ValueError:
            cfg["llm"]["temperature"] = 0.1
    if "OMNIROUTE_BASE_URL" in env:
        cfg["llm"]["omniroute_base_url"] = env["OMNIROUTE_BASE_URL"]
    if "OMNIROUTE_API_KEY" in env:
        cfg["llm"]["omniroute_api_key"] = env["OMNIROUTE_API_KEY"]
    if "OMNIROUTE_MODEL" in env:
        cfg["llm"]["omniroute_model"] = env["OMNIROUTE_MODEL"]

    # STT
    if "STT_BACKEND" in env:
        cfg["stt"]["backend"] = env["STT_BACKEND"]
    if "DEEPGRAM_API_KEY" in env:
        cfg["stt"]["deepgram_api_key"] = env["DEEPGRAM_API_KEY"]
    if "DEEPGRAM_MODEL" in env:
        cfg["stt"]["deepgram_model"] = env["DEEPGRAM_MODEL"]
    if "DEEPGRAM_LANGUAGE" in env:
        cfg["stt"]["deepgram_language"] = env["DEEPGRAM_LANGUAGE"]
    if "DEEPGRAM_FLUX_MODEL" in env:
        cfg["stt"]["deepgram_flux_model"] = env["DEEPGRAM_FLUX_MODEL"]
    if "CLOUD_STT_PROVIDER" in env:
        cfg["stt"]["cloud_provider"] = env["CLOUD_STT_PROVIDER"]
    if "CLOUD_STT_API_KEY" in env:
        cfg["stt"]["cloud_api_key"] = env["CLOUD_STT_API_KEY"]
    if "CLOUD_STT_BASE_URL" in env:
        cfg["stt"]["cloud_base_url"] = env["CLOUD_STT_BASE_URL"]
    if "CLOUD_STT_MODEL" in env:
        cfg["stt"]["cloud_model"] = env["CLOUD_STT_MODEL"]
    if "CLOUD_STT_LANGUAGE" in env:
        cfg["stt"]["cloud_language"] = env["CLOUD_STT_LANGUAGE"]
    if "PARAKEET_BINARY" in env:
        cfg["stt"]["parakeet_binary"] = env["PARAKEET_BINARY"]
    if "PARAKEET_MODEL" in env:
        cfg["stt"]["parakeet_model"] = env["PARAKEET_MODEL"]
    if "PARAKEET_STREAM_BINARY" in env:
        cfg["stt"]["parakeet_stream_binary"] = env["PARAKEET_STREAM_BINARY"]
    if "PARAKEET_STREAM_MODEL" in env:
        cfg["stt"]["parakeet_stream_model"] = env["PARAKEET_STREAM_MODEL"]

    # Profiles from gui_settings.json
    if "active_stt" in gui:
        cfg["profiles"]["active_stt"] = gui["active_stt"]
    if "active_clean" in gui:
        cfg["profiles"]["active_clean"] = gui["active_clean"]
    if "stt_profiles" in gui and isinstance(gui["stt_profiles"], dict):
        cfg["profiles"]["stt"] = gui["stt_profiles"]
    if "clean_profiles" in gui and isinstance(gui["clean_profiles"], dict):
        cfg["profiles"]["clean"] = gui["clean_profiles"]

    return cfg


def migrate_if_needed(
    config_path: Path | None = None,
    legacy_env_path: Path | None = None,
    legacy_gui_path: Path | None = None,
) -> bool:
    """Migrate legacy .env and gui_settings.json to config.toml if config.toml is missing.

    Writes config.toml with 0600 permissions. Leaves originals in place.
    Logs what was migrated without logging any secret values.
    Returns True if migration occurred, False otherwise.
    """
    config_file = config_path or get_config_path()
    if config_file.exists():
        return False

    repo_root = find_repo_root()
    data_dir = get_data_dir()

    # Locate legacy sources
    env_file = legacy_env_path
    if env_file is None:
        candidates = [
            Path.cwd() / ".env",
            (repo_root / ".env") if repo_root else None,
            data_dir.parent / ".env",
        ]
        for c in candidates:
            if c and c.is_file():
                env_file = c
                break

    gui_file = legacy_gui_path
    if gui_file is None:
        candidates = [
            data_dir / "gui_settings.json",
            (repo_root / "data" / "gui_settings.json") if repo_root else None,
            Path.cwd() / "data" / "gui_settings.json",
        ]
        for c in candidates:
            if c and c.is_file():
                gui_file = c
                break

    has_env = env_file is not None and env_file.is_file()
    has_gui = gui_file is not None and gui_file.is_file()

    if not has_env and not has_gui:
        return False

    env_data = parse_env_file(env_file) if (has_env and env_file) else {}
    gui_data = parse_gui_settings(gui_file) if (has_gui and gui_file) else {}

    migrated_cfg = build_migrated_config(env_data, gui_data)
    toml_str = dump_toml(migrated_cfg)

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(toml_str, encoding="utf-8")
    try:
        os.chmod(config_file, 0o600)
    except Exception as exc:
        log.warning("Failed to chmod 0600 on %s: %s", config_file, exc)

    # Log what was migrated WITHOUT logging secret values
    migrated_keys = sorted(env_data.keys())
    log.info(
        "Migrated configuration to %s (sources: env=%s, gui=%s). Settings migrated: %s",
        config_file,
        env_file if has_env else "none",
        gui_file if has_gui else "none",
        ", ".join(migrated_keys) if migrated_keys else "none",
    )
    if "stt_profiles" in gui_data:
        log.info(
            "Migrated STT profiles: %s (active: %s)",
            list(gui_data.get("stt_profiles", {}).keys()),
            gui_data.get("active_stt", "default"),
        )
    if "clean_profiles" in gui_data:
        log.info(
            "Migrated cleaning profiles: %s (active: %s)",
            list(gui_data.get("clean_profiles", {}).keys()),
            gui_data.get("active_clean", "default"),
        )

    return True
