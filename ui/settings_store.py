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
    "OMNIROUTE_BASE_URL",
    "OMNIROUTE_API_KEY",
    "OMNIROUTE_MODEL",
    "CLEANING_TEMPERATURE",
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
    "OMNIROUTE_BASE_URL": "http://127.0.0.1:20128",
    "OMNIROUTE_MODEL": "auto",
    "CLEANING_TEMPERATURE": "0.1",
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
    return values


def save_env(updates: dict[str, str]) -> None:
    """Merge updates into .env, preserving comments and unknown lines."""
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
    stt = {k: env.get(k, DEFAULTS.get(k, "")) for k in STT_FIELDS}
    clean = {k: env.get(k, DEFAULTS.get(k, "")) for k in CLEAN_FIELDS}
    return {
        "stt_profiles": {
            "Deepgram Cloud": dict(stt, STT_BACKEND="deepgram"),
            "Parakeet Local (batch)": dict(stt, STT_BACKEND="parakeet"),
            "Parakeet Stream (local)": dict(stt, STT_BACKEND="parakeet_stream"),
        },
        "active_stt": "Deepgram Cloud",
        "clean_profiles": {
            "Default": dict(clean),
        },
        "active_clean": "Default",
    }


def load_profiles() -> dict:
    env = load_env()
    try:
        data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "stt_profiles" in data:
            # Backfill any new fields added since the file was written.
            for prof in data.get("stt_profiles", {}).values():
                for k in STT_FIELDS:
                    prof.setdefault(k, env.get(k, DEFAULTS.get(k, "")))
            for prof in data.get("clean_profiles", {}).values():
                for k in CLEAN_FIELDS:
                    prof.setdefault(k, env.get(k, DEFAULTS.get(k, "")))
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
