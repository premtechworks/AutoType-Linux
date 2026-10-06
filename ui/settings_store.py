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
    values: dict[str, str] = dict(DEFAULTS)
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            values[key] = val.strip().strip("'\"")

    # Map legacy OMNIROUTE keys to LLM_* if LLM_* not set
    if "OMNIROUTE_BASE_URL" in values and "LLM_BASE_URL" not in values:
        values["LLM_BASE_URL"] = values["OMNIROUTE_BASE_URL"]
    if "OMNIROUTE_API_KEY" in values and "LLM_API_KEY" not in values:
        values["LLM_API_KEY"] = values["OMNIROUTE_API_KEY"]
    if "OMNIROUTE_MODEL" in values and "LLM_MODEL" not in values:
        values["LLM_MODEL"] = values["OMNIROUTE_MODEL"]
    if "LLM_PROVIDER" not in values:
        if values.get("OMNIROUTE_BASE_URL"):
            values["LLM_PROVIDER"] = "custom"
        else:
            values["LLM_PROVIDER"] = "openai"

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
        "Ollama (Local)": dict(
            clean_base,
            LLM_PROVIDER="ollama",
            LLM_BASE_URL="http://localhost:11434/v1",
            LLM_MODEL="llama3.2",
            LLM_API_KEY="",
        ),
        "Custom API Provider": dict(
            clean_base,
            LLM_PROVIDER="custom",
            LLM_BASE_URL=env.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1"),
            LLM_API_KEY=env.get("OMNIROUTE_API_KEY", ""),
            LLM_MODEL=env.get("OMNIROUTE_MODEL", "auto"),
        ),
    }

    # If env has specific settings, preserve them
    active_clean = "Custom API Provider" if env.get("OMNIROUTE_BASE_URL") else "OpenAI (ChatGPT)"

    return {
        "stt_profiles": stt_profiles,
        "active_stt": "Deepgram (Cloud Streaming)",
        "clean_profiles": clean_profiles,
        "active_clean": active_clean,
    }


def load_profiles() -> dict:
    env = load_env()
    try:
        if PROFILES_PATH.exists():
            data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "stt_profiles" in data:
                # Backfill any new fields
                for prof in data.get("stt_profiles", {}).values():
                    for k in STT_FIELDS:
                        prof.setdefault(k, env.get(k, DEFAULTS.get(k, "")))
                for prof in data.get("clean_profiles", {}).values():
                    for k in CLEAN_FIELDS:
                        prof.setdefault(k, env.get(k, DEFAULTS.get(k, "")))
                    # Migrate OMNIROUTE keys to LLM_*
                    if "OMNIROUTE_BASE_URL" in prof and not prof.get("LLM_BASE_URL"):
                        prof["LLM_BASE_URL"] = prof["OMNIROUTE_BASE_URL"]
                    if "OMNIROUTE_API_KEY" in prof and not prof.get("LLM_API_KEY"):
                        prof["LLM_API_KEY"] = prof["OMNIROUTE_API_KEY"]
                    if "OMNIROUTE_MODEL" in prof and not prof.get("LLM_MODEL"):
                        prof["LLM_MODEL"] = prof["OMNIROUTE_MODEL"]
                    if not prof.get("LLM_PROVIDER"):
                        prof["LLM_PROVIDER"] = "custom"
                return data
    except Exception:
        pass
    data = _seed_profiles(env)
    save_profiles(data)
    return data


def save_profiles(data: dict) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
