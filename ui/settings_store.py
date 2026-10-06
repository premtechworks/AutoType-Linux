"""Persistence layer for the Settings GUI.

Two stores:
  .env                    — source of truth the daemon (config.py) reads.
  data/gui_settings.json  — named STT + cleaning profiles to save/switch.
  data/custom_prompt.txt  — user-edited cleaning prompt.
  data/vocabulary.json    — personal vocabulary terms.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
PROFILES_PATH = BASE_DIR / "data" / "gui_settings.json"
CUSTOM_PROMPT_PATH = BASE_DIR / "data" / "custom_prompt.txt"
VOCAB_PATH = BASE_DIR / "data" / "vocabulary.json"

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
    "PARAKEET_BINARY": "/home/prem/projects/transcribe.cpp/build/bin/transcribe-cli",
    "PARAKEET_MODEL": "/home/prem/projects/AutoType/models/parakeet-tdt-0.6b-v2-Q4_K_M.gguf",
    "PARAKEET_STREAM_BINARY": "/home/prem/projects/parakeet.cpp/parakeet-cli",
    "PARAKEET_STREAM_MODEL": "/home/prem/projects/AutoType/models/parakeet-eou-120m-q8_0.gguf",
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


# -- .env ---------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Parse .env directly into a clean dict, prioritizing existing user settings."""
    raw: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raw[key] = val.strip().strip("'\"")

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
    """Merge updates into .env, preserving comments and unknown lines."""
    # If LLM_* keys are present, sync OMNIROUTE_* for backwards compatibility
    if "LLM_BASE_URL" in updates and "OMNIROUTE_BASE_URL" not in updates:
        updates["OMNIROUTE_BASE_URL"] = updates["LLM_BASE_URL"]
    if "LLM_API_KEY" in updates and "OMNIROUTE_API_KEY" not in updates:
        updates["OMNIROUTE_API_KEY"] = updates["LLM_API_KEY"]
    if "LLM_MODEL" in updates and "OMNIROUTE_MODEL" not in updates:
        updates["OMNIROUTE_MODEL"] = updates["LLM_MODEL"]

    lines: list[str] = []
    seen: set[str] = set()
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
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

    # Cloud and Local STT profiles
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

    # Cleaning LLM profiles
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

    # Determine active profiles from .env
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
    """Load gui_settings.json, always ensuring active profiles match the current .env state."""
    env = load_env()
    seeded = _seed_profiles(env)

    try:
        if PROFILES_PATH.exists():
            data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                stt_profs = data.setdefault("stt_profiles", {})
                clean_profs = data.setdefault("clean_profiles", {})

                # Merge any missing standard presets from seed
                for name, p_data in seeded["clean_profiles"].items():
                    if name not in clean_profs:
                        clean_profs[name] = dict(p_data)
                for name, p_data in seeded["stt_profiles"].items():
                    if name not in stt_profs:
                        stt_profs[name] = dict(p_data)

                # Migrate and backfill clean_profiles
                for name, prof in clean_profs.items():
                    if prof.get("OMNIROUTE_BASE_URL") and not prof.get("LLM_BASE_URL"):
                        prof["LLM_BASE_URL"] = prof["OMNIROUTE_BASE_URL"]
                    if prof.get("OMNIROUTE_API_KEY") and not prof.get("LLM_API_KEY"):
                        prof["LLM_API_KEY"] = prof["OMNIROUTE_API_KEY"]
                    if prof.get("OMNIROUTE_MODEL") and not prof.get("LLM_MODEL"):
                        prof["LLM_MODEL"] = prof["OMNIROUTE_MODEL"]

                    if not prof.get("LLM_PROVIDER"):
                        if name == "Custom API Provider" or prof.get("OMNIROUTE_BASE_URL"):
                            prof["LLM_PROVIDER"] = "custom"
                        else:
                            prof["LLM_PROVIDER"] = "openai"

                    for k in CLEAN_FIELDS:
                        prof.setdefault(k, DEFAULTS.get(k, ""))

                # Backfill stt_profiles
                for prof in stt_profs.values():
                    for k in STT_FIELDS:
                        prof.setdefault(k, DEFAULTS.get(k, ""))

                # Ensure active_clean correctly reflects .env
                active_clean = data.get("active_clean")
                if not active_clean or active_clean not in clean_profs or active_clean == "Default":
                    active_clean = seeded["active_clean"]
                    data["active_clean"] = active_clean

                # Synchronize the active profile with current .env values
                if active_clean in clean_profs:
                    for k in CLEAN_FIELDS:
                        if k in env and env[k]:
                            clean_profs[active_clean][k] = env[k]

                # If .env is custom, also synchronize Custom API Provider
                if env.get("LLM_PROVIDER") == "custom" and "Custom API Provider" in clean_profs:
                    for k in CLEAN_FIELDS:
                        if k in env and env[k]:
                            clean_profs["Custom API Provider"][k] = env[k]

                # Synchronize active_stt with current .env values
                active_stt = data.get("active_stt")
                if not active_stt or active_stt not in stt_profs:
                    active_stt = seeded["active_stt"]
                    data["active_stt"] = active_stt

                if active_stt in stt_profs:
                    for k in STT_FIELDS:
                        if k in env and env[k]:
                            stt_profs[active_stt][k] = env[k]

                return data
    except Exception:
        pass

    save_profiles(seeded)
    return seeded


def save_profiles(data: dict) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
    VOCAB_PATH.write_text(json.dumps({"terms": terms}, indent=2),
                           encoding="utf-8")
