"""Central configuration management for AutoType.

Consolidates all settings into $XDG_CONFIG_HOME/autotype/config.toml.
Environment variables still override config values, so advanced users
and existing .env workflows keep working.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from autotype.migration import migrate_if_needed
from autotype import paths
from autotype.paths import (
    find_repo_root,
    get_bin_dir,
    get_config_path,
    get_data_dir,
    get_models_dir,
)
from autotype.toml_io import dump_toml, load_toml

log = logging.getLogger("autotype.config")

# Load .env for environment variable support
load_dotenv()

# Run first-run migration if config.toml does not exist yet
migrate_if_needed()

DEFAULT_PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "custom": "http://127.0.0.1:20128/v1",
}

DEFAULT_PROVIDER_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "xai": "grok-2-mini",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "nvidia": "meta/llama-3.3-70b-instruct",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.3-70b-instruct",
    "ollama": "llama3.2",
    "custom": "auto",
}

VALID_MODES = (
    "raw",
    "clean",
    "smart",
    "professional",
    "casual",
    "email",
    "chat",
    "code",
)


def load_config() -> dict[str, Any]:
    """Read the consolidated config.toml, or return an empty dict if missing."""
    path = get_config_path()
    if path.is_file():
        try:
            return load_toml(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to parse %s: %s", path, exc)
    return {}


def save_config(cfg: dict[str, Any]) -> None:
    """Save configuration to config.toml with 0600 permissions."""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump_toml(cfg)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception as exc:
        log.warning("Failed to chmod 0600 on %s: %s", path, exc)


def _get_setting(env_name: str, section: str, key: str, default: Any = "") -> Any:
    """Get a configuration setting with Env > TOML > Default precedence."""
    # 1. Environment variable override
    val = os.getenv(env_name)
    if val is not None and val.strip() != "":
        return val.strip()

    # 2. TOML file setting
    cfg = load_config()
    sec = cfg.get(section, {})
    if isinstance(sec, dict) and key in sec:
        sec_val = sec[key]
        if sec_val is not None:
            return sec_val

    # 3. Default
    return default


def _get_str(env_name: str, section: str, key: str, default: str = "") -> str:
    res = _get_setting(env_name, section, key, default)
    return str(res).strip() if res is not None else default


def _get_bool(env_name: str, section: str, key: str, default: bool = False) -> bool:
    res = _get_setting(env_name, section, key, default)
    if isinstance(res, bool):
        return res
    return str(res).strip().lower() in ("1", "true", "yes")


def _get_float(env_name: str, section: str, key: str, default: float = 0.1) -> float:
    res = _get_setting(env_name, section, key, default)
    try:
        return float(res)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# LLM Text Cleaning Provider Settings
# ---------------------------------------------------------------------------

def llm_provider() -> str:
    """Selected cleaning provider: openai, anthropic, xai, deepseek, qwen, nvidia, groq, ollama, custom."""
    prov = _get_str("LLM_PROVIDER", "llm", "provider", "").lower()
    if prov:
        return prov
    # Backward compatibility with existing OMNIROUTE configs
    if _get_str("OMNIROUTE_BASE_URL", "llm", "omniroute_base_url", ""):
        return "custom"
    return "openai"


def llm_base_url() -> str:
    """Base API endpoint for LLM text cleanup."""
    url = _get_str("LLM_BASE_URL", "llm", "base_url", "") or _get_str(
        "OMNIROUTE_BASE_URL", "llm", "omniroute_base_url", ""
    )
    if url:
        return url.rstrip("/")
    prov = llm_provider()
    return DEFAULT_PROVIDER_URLS.get(prov, DEFAULT_PROVIDER_URLS["openai"])


def llm_api_key() -> str:
    """API key for the selected cleaning provider."""
    return _get_str("LLM_API_KEY", "llm", "api_key", "") or _get_str(
        "OMNIROUTE_API_KEY", "llm", "omniroute_api_key", ""
    )


def llm_model() -> str:
    """Model identifier for text cleanup."""
    model = _get_str("LLM_MODEL", "llm", "model", "") or _get_str(
        "OMNIROUTE_MODEL", "llm", "omniroute_model", ""
    )
    if model:
        return model
    prov = llm_provider()
    return DEFAULT_PROVIDER_MODELS.get(prov, "gpt-4o-mini")


# Backwards compatibility wrappers
def omniroute_base_url() -> str:
    return llm_base_url()


def omniroute_api_key() -> str:
    return llm_api_key()


def omniroute_model() -> str:
    return llm_model()


def cleaning_temperature() -> float:
    return _get_float("CLEANING_TEMPERATURE", "llm", "temperature", 0.1)


# ---------------------------------------------------------------------------
# Speech-to-Text (STT) Settings: Cloud vs Local
# ---------------------------------------------------------------------------

def stt_backend() -> str:
    """Active backend: deepgram, whisper, openai, groq, nvidia, custom_cloud, parakeet, parakeet_stream."""
    backend = _get_str("STT_BACKEND", "stt", "backend", "deepgram").lower()
    return backend or "deepgram"


def is_cloud_stt() -> bool:
    return stt_backend() in ("deepgram", "whisper", "openai", "groq", "nvidia", "custom_cloud")


def is_local_stt() -> bool:
    return stt_backend() in ("parakeet", "parakeet_stream")


# Cloud STT: Deepgram
def deepgram_api_key() -> str:
    return _get_str("DEEPGRAM_API_KEY", "stt", "deepgram_api_key", "") or _get_str(
        "CLOUD_STT_API_KEY", "stt", "cloud_api_key", ""
    )


def deepgram_model() -> str:
    return _get_str("DEEPGRAM_MODEL", "stt", "deepgram_model", "nova-3") or "nova-3"


def deepgram_language() -> str:
    return _get_str("DEEPGRAM_LANGUAGE", "stt", "deepgram_language", "en-US") or "en-US"


def deepgram_flux_model() -> str:
    return _get_str("DEEPGRAM_FLUX_MODEL", "stt", "deepgram_flux_model", "flux-general-en") or "flux-general-en"


# Cloud STT: OpenAI Whisper / Groq / NVIDIA / Custom Cloud
def cloud_stt_provider() -> str:
    return _get_str("CLOUD_STT_PROVIDER", "stt", "cloud_provider", "deepgram").lower() or "deepgram"


def cloud_stt_api_key() -> str:
    return _get_str("CLOUD_STT_API_KEY", "stt", "cloud_api_key", "") or _get_str(
        "DEEPGRAM_API_KEY", "stt", "deepgram_api_key", ""
    )


def cloud_stt_base_url() -> str:
    return _get_str("CLOUD_STT_BASE_URL", "stt", "cloud_base_url", "https://api.openai.com/v1") or "https://api.openai.com/v1"


def cloud_stt_model() -> str:
    return _get_str("CLOUD_STT_MODEL", "stt", "cloud_model", "whisper-1") or "whisper-1"


def cloud_stt_language() -> str:
    return _get_str("CLOUD_STT_LANGUAGE", "stt", "cloud_language", "en") or "en"


# Local STT: Parakeet & Parakeet Stream Path Auto-Resolution
def resolve_local_binary(filename: str) -> str:
    """Resolve binary path: check XDG bin dir, then dev repo, or default to XDG bin path."""
    xdg_bin = paths.get_bin_dir() / filename
    if xdg_bin.is_file():
        return str(xdg_bin)
    repo = paths.find_repo_root()
    if repo:
        dev_cand = repo / filename
        if dev_cand.is_file():
            return str(dev_cand)
    return str(xdg_bin)


def resolve_local_model(filename: str) -> str:
    """Resolve model path: check XDG models dir, then dev repo models dir, or default to XDG model path."""
    xdg_model = paths.get_models_dir() / filename
    if xdg_model.is_file():
        return str(xdg_model)
    repo = paths.find_repo_root()
    if repo:
        dev_cand = repo / "models" / filename
        if dev_cand.is_file():
            return str(dev_cand)
    return str(xdg_model)


def parakeet_binary() -> str:
    env_val = os.getenv("PARAKEET_BINARY")
    if env_val is not None and env_val.strip():
        return env_val.strip()
    cfg = load_config()
    stt_sec = cfg.get("stt", {})
    if isinstance(stt_sec, dict) and stt_sec.get("parakeet_binary"):
        return str(stt_sec["parakeet_binary"]).strip()
    return resolve_local_binary("transcribe-cli")


def parakeet_model() -> str:
    env_val = os.getenv("PARAKEET_MODEL")
    if env_val is not None and env_val.strip():
        return env_val.strip()
    cfg = load_config()
    stt_sec = cfg.get("stt", {})
    if isinstance(stt_sec, dict) and stt_sec.get("parakeet_model"):
        return str(stt_sec["parakeet_model"]).strip()
    return resolve_local_model("parakeet-tdt-0.6b-v2-Q4_K_M.gguf")


def parakeet_stream_binary() -> str:
    env_val = os.getenv("PARAKEET_STREAM_BINARY")
    if env_val is not None and env_val.strip():
        return env_val.strip()
    cfg = load_config()
    stt_sec = cfg.get("stt", {})
    if isinstance(stt_sec, dict) and stt_sec.get("parakeet_stream_binary"):
        return str(stt_sec["parakeet_stream_binary"]).strip()
    return resolve_local_binary("parakeet-cli")


def parakeet_stream_model() -> str:
    env_val = os.getenv("PARAKEET_STREAM_MODEL")
    if env_val is not None and env_val.strip():
        return env_val.strip()
    cfg = load_config()
    stt_sec = cfg.get("stt", {})
    if isinstance(stt_sec, dict) and stt_sec.get("parakeet_stream_model"):
        return str(stt_sec["parakeet_stream_model"]).strip()
    return resolve_local_model("parakeet-eou-120m-q8_0.gguf")


# ---------------------------------------------------------------------------
# Desktop, Audio & Mode Settings
# ---------------------------------------------------------------------------

def processing_mode() -> str:
    mode = _get_str("PROCESSING_MODE", "general", "processing_mode", "clean").lower()
    return mode if mode in VALID_MODES else "clean"


def command_prefix() -> str:
    return _get_str("COMMAND_PREFIX", "general", "command_prefix", "computer") or "computer"


def mic_device() -> str:
    """Preferred mic: "" = follow the system via the ALSA "pipewire" device."""
    return _get_str("MIC_DEVICE", "general", "mic_device", "")


def save_recordings() -> bool:
    return _get_bool("SAVE_RECORDINGS", "general", "save_recordings", False)


def use_custom_prompt() -> bool:
    return _get_bool("USE_CUSTOM_PROMPT", "general", "use_custom_prompt", False)


def custom_prompt_path() -> str:
    custom = _get_str("CUSTOM_PROMPT_FILE", "general", "custom_prompt_file", "")
    if custom:
        return custom
    return str(get_data_dir() / "custom_prompt.txt")


def custom_prompt() -> str:
    """User-edited cleaning prompt (empty = not set)."""
    try:
        text = Path(custom_prompt_path()).read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    return text


def first_run_completed() -> bool:
    """Check whether the first-run setup prompt has been completed or dismissed."""
    return _get_bool("FIRST_RUN_COMPLETED", "general", "first_run_completed", False)


def set_first_run_completed(completed: bool = True) -> None:
    """Store first-run prompt dismissal in config.toml."""
    cfg = load_config()
    if "general" not in cfg or not isinstance(cfg["general"], dict):
        cfg["general"] = {}
    cfg["general"]["first_run_completed"] = completed
    save_config(cfg)

