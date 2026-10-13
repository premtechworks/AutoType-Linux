"""Persistence layer for the Settings GUI.

Uses config.toml located at $XDG_CONFIG_HOME/autotype/config.toml (or ~/.config/autotype/config.toml)
as the primary source of truth, while preserving environment variable overrides and .env updates.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from autotype.config import load_config, save_config
from autotype.paths import find_repo_root, get_config_path, get_data_dir

BASE_DIR = find_repo_root() or Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
CUSTOM_PROMPT_PATH = get_data_dir() / "custom_prompt.txt"
VOCAB_PATH = get_data_dir() / "vocabulary.json"

STT_FIELDS = (
    "STT_BACKEND",
    "STT_TYPE",
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
)

CLEAN_FIELDS = (
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "CLEANING_TEMPERATURE",
    "OMNIROUTE_BASE_URL",
    "OMNIROUTE_API_KEY",
    "OMNIROUTE_MODEL",
)

GLOBAL_FIELDS = (
    "PROCESSING_MODE",
    "COMMAND_PREFIX",
    "SAVE_RECORDINGS",
    "MIC_DEVICE",
    "USE_CUSTOM_PROMPT",
)

DEFAULTS = {
    "STT_BACKEND": "deepgram",
    "STT_TYPE": "cloud",
    "CLOUD_STT_PROVIDER": "deepgram",
    "CLOUD_STT_BASE_URL": "https://api.openai.com/v1",
    "CLOUD_STT_MODEL": "whisper-1",
    "CLOUD_STT_LANGUAGE": "en",
    "DEEPGRAM_MODEL": "nova-3",
    "DEEPGRAM_LANGUAGE": "en-US",
    "DEEPGRAM_FLUX_MODEL": "flux-general-en",
    "PARAKEET_BINARY": "",
    "PARAKEET_MODEL": "",
    "PARAKEET_STREAM_BINARY": "",
    "PARAKEET_STREAM_MODEL": "",
    "PROCESSING_MODE": "clean",
    "SAVE_RECORDINGS": "false",
    "COMMAND_PREFIX": "computer",
    "LLM_PROVIDER": "openai",
    "LLM_BASE_URL": "https://api.openai.com/v1",
    "LLM_MODEL": "gpt-4o-mini",
    "CLEANING_TEMPERATURE": "0.1",
    "OMNIROUTE_BASE_URL": "http://127.0.0.1:20128/v1",
    "OMNIROUTE_MODEL": "auto",
    "MIC_DEVICE": "",
    "USE_CUSTOM_PROMPT": "false",
}


# -- config.toml & env loading -----------------------------------------------

def load_env() -> dict[str, str]:
    """Parse configuration into a dict for the settings GUI."""
    cfg = load_config()
    raw: dict[str, str] = {}

    # Extract from config.toml
    gen = cfg.get("general", {})
    if isinstance(gen, dict):
        if "processing_mode" in gen:
            raw["PROCESSING_MODE"] = str(gen["processing_mode"])
        if "command_prefix" in gen:
            raw["COMMAND_PREFIX"] = str(gen["command_prefix"])
        if "save_recordings" in gen:
            raw["SAVE_RECORDINGS"] = str(gen["save_recordings"]).lower()
        if "use_custom_prompt" in gen:
            raw["USE_CUSTOM_PROMPT"] = str(gen["use_custom_prompt"]).lower()
        if "custom_prompt_file" in gen:
            raw["CUSTOM_PROMPT_FILE"] = str(gen["custom_prompt_file"])
        if "mic_device" in gen:
            raw["MIC_DEVICE"] = str(gen["mic_device"])

    llm = cfg.get("llm", {})
    if isinstance(llm, dict):
        if "provider" in llm:
            raw["LLM_PROVIDER"] = str(llm["provider"])
        if "base_url" in llm:
            raw["LLM_BASE_URL"] = str(llm["base_url"])
        if "api_key" in llm:
            raw["LLM_API_KEY"] = str(llm["api_key"])
        if "model" in llm:
            raw["LLM_MODEL"] = str(llm["model"])
        if "temperature" in llm:
            raw["CLEANING_TEMPERATURE"] = str(llm["temperature"])
        if "omniroute_base_url" in llm:
            raw["OMNIROUTE_BASE_URL"] = str(llm["omniroute_base_url"])
        if "omniroute_api_key" in llm:
            raw["OMNIROUTE_API_KEY"] = str(llm["omniroute_api_key"])
        if "omniroute_model" in llm:
            raw["OMNIROUTE_MODEL"] = str(llm["omniroute_model"])

    stt = cfg.get("stt", {})
    if isinstance(stt, dict):
        if "backend" in stt:
            raw["STT_BACKEND"] = str(stt["backend"])
        if "deepgram_api_key" in stt:
            raw["DEEPGRAM_API_KEY"] = str(stt["deepgram_api_key"])
        if "deepgram_model" in stt:
            raw["DEEPGRAM_MODEL"] = str(stt["deepgram_model"])
        if "deepgram_language" in stt:
            raw["DEEPGRAM_LANGUAGE"] = str(stt["deepgram_language"])
        if "deepgram_flux_model" in stt:
            raw["DEEPGRAM_FLUX_MODEL"] = str(stt["deepgram_flux_model"])
        if "cloud_provider" in stt:
            raw["CLOUD_STT_PROVIDER"] = str(stt["cloud_provider"])
        if "cloud_api_key" in stt:
            raw["CLOUD_STT_API_KEY"] = str(stt["cloud_api_key"])
        if "cloud_base_url" in stt:
            raw["CLOUD_STT_BASE_URL"] = str(stt["cloud_base_url"])
        if "cloud_model" in stt:
            raw["CLOUD_STT_MODEL"] = str(stt["cloud_model"])
        if "cloud_language" in stt:
            raw["CLOUD_STT_LANGUAGE"] = str(stt["cloud_language"])
        if "parakeet_binary" in stt:
            raw["PARAKEET_BINARY"] = str(stt["parakeet_binary"])
        if "parakeet_model" in stt:
            raw["PARAKEET_MODEL"] = str(stt["parakeet_model"])
        if "parakeet_stream_binary" in stt:
            raw["PARAKEET_STREAM_BINARY"] = str(stt["parakeet_stream_binary"])
        if "parakeet_stream_model" in stt:
            raw["PARAKEET_STREAM_MODEL"] = str(stt["parakeet_stream_model"])

    # Also overlay current environment variables if set
    for field in list(STT_FIELDS) + list(CLEAN_FIELDS) + list(GLOBAL_FIELDS):
        val = os.getenv(field)
        if val is not None and val.strip() != "":
            raw[field] = val.strip()

    # 1. Backwards compatibility for LLM Cleaning Provider:
    has_omniroute = bool(raw.get("OMNIROUTE_BASE_URL") or raw.get("OMNIROUTE_API_KEY") or raw.get("OMNIROUTE_MODEL"))

    if "LLM_PROVIDER" not in raw:
        if has_omniroute:
            raw["LLM_PROVIDER"] = "custom"
        else:
            raw["LLM_PROVIDER"] = DEFAULTS["LLM_PROVIDER"]

    if "LLM_BASE_URL" not in raw:
        if raw.get("OMNIROUTE_BASE_URL"):
            raw["LLM_BASE_URL"] = raw["OMNIROUTE_BASE_URL"]
        else:
            raw["LLM_BASE_URL"] = DEFAULTS.get("LLM_BASE_URL", "")

    if "LLM_API_KEY" not in raw:
        if raw.get("OMNIROUTE_API_KEY"):
            raw["LLM_API_KEY"] = raw["OMNIROUTE_API_KEY"]
        else:
            raw["LLM_API_KEY"] = ""

    if "LLM_MODEL" not in raw:
        if raw.get("OMNIROUTE_MODEL"):
            raw["LLM_MODEL"] = raw["OMNIROUTE_MODEL"]
        else:
            raw["LLM_MODEL"] = DEFAULTS.get("LLM_MODEL", "gpt-4o-mini")

    # Keep OMNIROUTE_* synced with LLM_*
    if "LLM_BASE_URL" in raw and "OMNIROUTE_BASE_URL" not in raw:
        raw["OMNIROUTE_BASE_URL"] = raw["LLM_BASE_URL"]
    if "LLM_API_KEY" in raw and "OMNIROUTE_API_KEY" not in raw:
        raw["OMNIROUTE_API_KEY"] = raw["LLM_API_KEY"]
    if "LLM_MODEL" in raw and "OMNIROUTE_MODEL" not in raw:
        raw["OMNIROUTE_MODEL"] = raw["LLM_MODEL"]

    # 2. Backwards compatibility for STT:
    if "STT_BACKEND" not in raw:
        raw["STT_BACKEND"] = DEFAULTS["STT_BACKEND"]
    if raw.get("STT_BACKEND") in ("parakeet", "parakeet_stream"):
        raw["STT_TYPE"] = "local"
    else:
        raw["STT_TYPE"] = "cloud"

    # Fill in any missing default keys without overriding raw values
    values = dict(DEFAULTS)
    values.update(raw)
    return values


def save_env(updates: dict[str, str]) -> None:
    """Save updates to config.toml and keep .env in sync if it exists."""
    # If LLM_* keys are present, sync OMNIROUTE_* for backwards compatibility
    if "LLM_BASE_URL" in updates and "OMNIROUTE_BASE_URL" not in updates:
        updates["OMNIROUTE_BASE_URL"] = updates["LLM_BASE_URL"]
    if "LLM_API_KEY" in updates and "OMNIROUTE_API_KEY" not in updates:
        updates["OMNIROUTE_API_KEY"] = updates["LLM_API_KEY"]
    if "LLM_MODEL" in updates and "OMNIROUTE_MODEL" not in updates:
        updates["OMNIROUTE_MODEL"] = updates["LLM_MODEL"]

    cfg = load_config()
    gen = cfg.setdefault("general", {})
    llm = cfg.setdefault("llm", {})
    stt = cfg.setdefault("stt", {})

    # General
    if "PROCESSING_MODE" in updates:
        gen["processing_mode"] = updates["PROCESSING_MODE"]
    if "COMMAND_PREFIX" in updates:
        gen["command_prefix"] = updates["COMMAND_PREFIX"]
    if "SAVE_RECORDINGS" in updates:
        gen["save_recordings"] = updates["SAVE_RECORDINGS"].lower() in ("1", "true", "yes")
    if "USE_CUSTOM_PROMPT" in updates:
        gen["use_custom_prompt"] = updates["USE_CUSTOM_PROMPT"].lower() in ("1", "true", "yes")
    if "CUSTOM_PROMPT_FILE" in updates:
        gen["custom_prompt_file"] = updates["CUSTOM_PROMPT_FILE"]
    if "MIC_DEVICE" in updates:
        gen["mic_device"] = updates["MIC_DEVICE"]

    # LLM
    if "LLM_PROVIDER" in updates:
        llm["provider"] = updates["LLM_PROVIDER"]
    if "LLM_BASE_URL" in updates:
        llm["base_url"] = updates["LLM_BASE_URL"]
    if "LLM_API_KEY" in updates:
        llm["api_key"] = updates["LLM_API_KEY"]
    if "LLM_MODEL" in updates:
        llm["model"] = updates["LLM_MODEL"]
    if "CLEANING_TEMPERATURE" in updates:
        try:
            llm["temperature"] = float(updates["CLEANING_TEMPERATURE"])
        except ValueError:
            llm["temperature"] = 0.1
    if "OMNIROUTE_BASE_URL" in updates:
        llm["omniroute_base_url"] = updates["OMNIROUTE_BASE_URL"]
    if "OMNIROUTE_API_KEY" in updates:
        llm["omniroute_api_key"] = updates["OMNIROUTE_API_KEY"]
    if "OMNIROUTE_MODEL" in updates:
        llm["omniroute_model"] = updates["OMNIROUTE_MODEL"]

    # STT
    if "STT_BACKEND" in updates:
        stt["backend"] = updates["STT_BACKEND"]
    if "DEEPGRAM_API_KEY" in updates:
        stt["deepgram_api_key"] = updates["DEEPGRAM_API_KEY"]
    if "DEEPGRAM_MODEL" in updates:
        stt["deepgram_model"] = updates["DEEPGRAM_MODEL"]
    if "DEEPGRAM_LANGUAGE" in updates:
        stt["deepgram_language"] = updates["DEEPGRAM_LANGUAGE"]
    if "DEEPGRAM_FLUX_MODEL" in updates:
        stt["deepgram_flux_model"] = updates["DEEPGRAM_FLUX_MODEL"]
    if "CLOUD_STT_PROVIDER" in updates:
        stt["cloud_provider"] = updates["CLOUD_STT_PROVIDER"]
    if "CLOUD_STT_API_KEY" in updates:
        stt["cloud_api_key"] = updates["CLOUD_STT_API_KEY"]
    if "CLOUD_STT_BASE_URL" in updates:
        stt["cloud_base_url"] = updates["CLOUD_STT_BASE_URL"]
    if "CLOUD_STT_MODEL" in updates:
        stt["cloud_model"] = updates["CLOUD_STT_MODEL"]
    if "CLOUD_STT_LANGUAGE" in updates:
        stt["cloud_language"] = updates["CLOUD_STT_LANGUAGE"]
    if "PARAKEET_BINARY" in updates:
        stt["parakeet_binary"] = updates["PARAKEET_BINARY"]
    if "PARAKEET_MODEL" in updates:
        stt["parakeet_model"] = updates["PARAKEET_MODEL"]
    if "PARAKEET_STREAM_BINARY" in updates:
        stt["parakeet_stream_binary"] = updates["PARAKEET_STREAM_BINARY"]
    if "PARAKEET_STREAM_MODEL" in updates:
        stt["parakeet_stream_model"] = updates["PARAKEET_STREAM_MODEL"]

    save_config(cfg)

    # If .env exists, keep it updated as well
    if ENV_PATH.exists():
        lines: list[str] = ENV_PATH.read_text(encoding="utf-8").splitlines()
        seen: set[str] = set()
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key in updates:
                    out.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            out.append(line)
        for key, val in updates.items():
            if key not in seen:
                out.append(f"{key}={val}")
        ENV_PATH.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
        try:
            os.chmod(ENV_PATH, 0o600)
        except Exception:
            pass


# -- named profiles ------------------------------------------------------

def _seed_profiles(env: dict[str, str]) -> dict:
    stt_base = {k: env.get(k, DEFAULTS.get(k, "")) for k in STT_FIELDS}
    clean_base = {k: env.get(k, DEFAULTS.get(k, "")) for k in CLEAN_FIELDS}

    stt_profiles = {
        "Deepgram (Cloud Streaming)": dict(
            stt_base,
            STT_BACKEND="deepgram",
            STT_TYPE="cloud",
            CLOUD_STT_PROVIDER="deepgram",
        ),
        "OpenAI Whisper (Cloud)": dict(
            stt_base,
            STT_BACKEND="whisper",
            STT_TYPE="cloud",
            CLOUD_STT_PROVIDER="openai",
            CLOUD_STT_BASE_URL="https://api.openai.com/v1",
            CLOUD_STT_MODEL="whisper-1",
        ),
        "Groq Whisper (Cloud Fast)": dict(
            stt_base,
            STT_BACKEND="groq",
            STT_TYPE="cloud",
            CLOUD_STT_PROVIDER="groq",
            CLOUD_STT_BASE_URL="https://api.groq.com/openai/v1",
            CLOUD_STT_MODEL="whisper-large-v3-turbo",
        ),
        "NVIDIA Cloud ASR": dict(
            stt_base,
            STT_BACKEND="nvidia",
            STT_TYPE="cloud",
            CLOUD_STT_PROVIDER="nvidia",
            CLOUD_STT_BASE_URL="https://integrate.api.nvidia.com/v1",
            CLOUD_STT_MODEL="nvidia/parakeet-ctc-1.1b-asr",
        ),
        "Parakeet Stream (Local Offline)": dict(
            stt_base,
            STT_BACKEND="parakeet_stream",
            STT_TYPE="local",
        ),
        "Parakeet Batch (Local Offline)": dict(
            stt_base,
            STT_BACKEND="parakeet",
            STT_TYPE="local",
        ),
    }

    clean_profiles = {
        "Custom API Provider": dict(
            clean_base,
            LLM_PROVIDER="custom",
            LLM_BASE_URL=env.get("OMNIROUTE_BASE_URL") or env.get("LLM_BASE_URL") or "http://127.0.0.1:20128/v1",
            LLM_API_KEY=env.get("OMNIROUTE_API_KEY") or env.get("LLM_API_KEY") or "",
            LLM_MODEL=env.get("OMNIROUTE_MODEL") or env.get("LLM_MODEL") or "auto",
        ),
        "OpenAI (ChatGPT)": dict(
            clean_base,
            LLM_PROVIDER="openai",
            LLM_BASE_URL="https://api.openai.com/v1",
            LLM_MODEL="gpt-4o-mini",
        ),
        "Anthropic (Claude)": dict(
            clean_base,
            LLM_PROVIDER="anthropic",
            LLM_BASE_URL="https://api.anthropic.com/v1",
            LLM_MODEL="claude-3-5-haiku-20241022",
        ),
        "xAI (Grok)": dict(
            clean_base,
            LLM_PROVIDER="xai",
            LLM_BASE_URL="https://api.x.ai/v1",
            LLM_MODEL="grok-2-mini",
        ),
        "DeepSeek": dict(
            clean_base,
            LLM_PROVIDER="deepseek",
            LLM_BASE_URL="https://api.deepseek.com/v1",
            LLM_MODEL="deepseek-chat",
        ),
        "Qwen (Alibaba)": dict(
            clean_base,
            LLM_PROVIDER="qwen",
            LLM_BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            LLM_MODEL="qwen-plus",
        ),
        "NVIDIA NIM": dict(
            clean_base,
            LLM_PROVIDER="nvidia",
            LLM_BASE_URL="https://integrate.api.nvidia.com/v1",
            LLM_MODEL="meta/llama-3.3-70b-instruct",
        ),
        "Groq": dict(
            clean_base,
            LLM_PROVIDER="groq",
            LLM_BASE_URL="https://api.groq.com/openai/v1",
            LLM_MODEL="llama-3.3-70b-versatile",
        ),
        "OpenRouter": dict(
            clean_base,
            LLM_PROVIDER="openrouter",
            LLM_BASE_URL="https://openrouter.ai/api/v1",
            LLM_MODEL="meta-llama/llama-3.3-70b-instruct",
        ),
        "Ollama (Local)": dict(
            clean_base,
            LLM_PROVIDER="ollama",
            LLM_BASE_URL="http://localhost:11434/v1",
            LLM_MODEL="llama3.2",
            LLM_API_KEY="",
        ),
    }

    is_custom = env.get("LLM_PROVIDER") == "custom" or bool(env.get("OMNIROUTE_BASE_URL"))
    active_clean = "Custom API Provider" if is_custom else "OpenAI (ChatGPT)"

    stt_backend = env.get("STT_BACKEND", "deepgram")
    if stt_backend == "parakeet_stream":
        active_stt = "Parakeet Stream (Local Offline)"
    elif stt_backend == "parakeet":
        active_stt = "Parakeet Batch (Local Offline)"
    elif stt_backend == "groq":
        active_stt = "Groq Whisper (Cloud Fast)"
    elif stt_backend in ("whisper", "openai"):
        active_stt = "OpenAI Whisper (Cloud)"
    elif stt_backend == "nvidia":
        active_stt = "NVIDIA Cloud ASR"
    else:
        active_stt = "Deepgram (Cloud Streaming)"

    return {
        "stt_profiles": stt_profiles,
        "active_stt": active_stt,
        "clean_profiles": clean_profiles,
        "active_clean": active_clean,
    }


def load_profiles() -> dict:
    """Load profiles from config.toml (or fallback to legacy gui_settings.json)."""
    env = load_env()
    seeded = _seed_profiles(env)

    cfg = load_config()
    profs_section = cfg.get("profiles")

    if isinstance(profs_section, dict) and "stt_profiles" in profs_section:
        data = profs_section
    elif isinstance(profs_section, dict) and "stt" in profs_section:
        # TOML format with profiles.stt and profiles.clean
        data = {
            "stt_profiles": profs_section.get("stt", {}),
            "clean_profiles": profs_section.get("clean", {}),
            "active_stt": profs_section.get("active_stt", seeded["active_stt"]),
            "active_clean": profs_section.get("active_clean", seeded["active_clean"]),
        }
    else:
        # Fallback to legacy gui_settings.json if present
        legacy_path = get_data_dir() / "gui_settings.json"
        if legacy_path.exists():
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
            except Exception:
                data = seeded
        else:
            data = seeded

    stt_profs = data.setdefault("stt_profiles", {})
    clean_profs = data.setdefault("clean_profiles", {})

    for name, p_data in seeded["clean_profiles"].items():
        if name not in clean_profs:
            clean_profs[name] = dict(p_data)
    for name, p_data in seeded["stt_profiles"].items():
        if name not in stt_profs:
            stt_profs[name] = dict(p_data)

    save_profiles(data)
    return data


def save_profiles(data: dict) -> None:
    """Save profiles to config.toml."""
    cfg = load_config()
    cfg["profiles"] = data
    save_config(cfg)


def reset_clean_defaults() -> dict[str, str]:
    """Reset cleaning settings to default OpenAI configuration."""
    clean_defaults = {
        "LLM_PROVIDER": "openai",
        "LLM_BASE_URL": "https://api.openai.com/v1",
        "LLM_API_KEY": "",
        "LLM_MODEL": "gpt-4o-mini",
        "CLEANING_TEMPERATURE": "0.1",
        "OMNIROUTE_BASE_URL": "https://api.openai.com/v1",
        "OMNIROUTE_API_KEY": "",
        "OMNIROUTE_MODEL": "gpt-4o-mini",
    }
    save_env(clean_defaults)
    try:
        profiles = load_profiles()
        profiles["active_clean"] = "OpenAI (ChatGPT)"
        if "OpenAI (ChatGPT)" in profiles.get("clean_profiles", {}):
            profiles["clean_profiles"]["OpenAI (ChatGPT)"].update(clean_defaults)
        save_profiles(profiles)
    except Exception:
        pass
    return clean_defaults


def reset_stt_defaults() -> dict[str, str]:
    """Reset STT settings to default Deepgram Cloud Streaming configuration."""
    stt_defaults = {
        "STT_BACKEND": "deepgram",
        "STT_TYPE": "cloud",
        "CLOUD_STT_PROVIDER": "deepgram",
        "DEEPGRAM_MODEL": "nova-3",
        "DEEPGRAM_LANGUAGE": "en-US",
        "DEEPGRAM_FLUX_MODEL": "flux-general-en",
    }
    save_env(stt_defaults)
    try:
        profiles = load_profiles()
        profiles["active_stt"] = "Deepgram (Cloud Streaming)"
        if "Deepgram (Cloud Streaming)" in profiles.get("stt_profiles", {}):
            profiles["stt_profiles"]["Deepgram (Cloud Streaming)"].update(stt_defaults)
        save_profiles(profiles)
    except Exception:
        pass
    return stt_defaults


# -- custom prompt + vocabulary ------------------------------------------

def load_custom_prompt() -> str:
    try:
        return CUSTOM_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def save_custom_prompt(text: str) -> None:
    CUSTOM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_PROMPT_PATH.write_text(text, encoding="utf-8")


def load_vocabulary() -> list[str]:
    try:
        data = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
        terms = data.get("terms", []) if isinstance(data, dict) else []
        return [t for t in terms if isinstance(t, str)]
    except Exception:
        return []


def save_vocabulary(terms: list[str]) -> None:
    VOCAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOCAB_PATH.write_text(json.dumps({"terms": terms}, indent=2), encoding="utf-8")
