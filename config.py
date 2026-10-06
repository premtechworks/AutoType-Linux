"""Central config.

All settings and secrets come from .env — nothing hard-coded.
Supports any LLM Cleaning Provider (OpenAI, Anthropic Claude, xAI Grok,
DeepSeek, Qwen, NVIDIA NIM, Groq, Ollama, Custom/OmniRoute) and separate
Cloud STT vs Local Offline STT backends.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _required(name: str) -> str:
    value = _get(name)
    if not value:
        raise RuntimeError(
            f"Missing {name} in .env. Copy .env.example to .env and fill it in."
        )
    return value


# ---------------------------------------------------------------------------
# LLM Text Cleaning Provider Settings
# ---------------------------------------------------------------------------

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


def llm_provider() -> str:
    """Selected cleaning provider: openai, anthropic, xai, deepseek, qwen, nvidia, groq, ollama, custom."""
    prov = _get("LLM_PROVIDER").lower()
    if prov:
        return prov
    # Backward compatibility with existing OMNIROUTE configs
    if _get("OMNIROUTE_BASE_URL"):
        return "custom"
    return "openai"


def llm_base_url() -> str:
    """Base API endpoint for LLM text cleanup."""
    url = _get("LLM_BASE_URL") or _get("OMNIROUTE_BASE_URL")
    if url:
        return url.rstrip("/")
    prov = llm_provider()
    return DEFAULT_PROVIDER_URLS.get(prov, DEFAULT_PROVIDER_URLS["openai"])


def llm_api_key() -> str:
    """API key for the selected cleaning provider."""
    # Custom/Ollama may not require a key
    return _get("LLM_API_KEY") or _get("OMNIROUTE_API_KEY")


def llm_model() -> str:
    """Model identifier for text cleanup."""
    model = _get("LLM_MODEL") or _get("OMNIROUTE_MODEL")
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
    try:
        return float(_get("CLEANING_TEMPERATURE", "0.1") or 0.1)
    except ValueError:
        return 0.1


# ---------------------------------------------------------------------------
# Speech-to-Text (STT) Settings: Cloud vs Local
# ---------------------------------------------------------------------------

def stt_backend() -> str:
    """Active backend: deepgram, whisper, openai, groq, nvidia, custom_cloud, parakeet, parakeet_stream."""
    backend = _get("STT_BACKEND", "deepgram").lower()
    return backend or "deepgram"


def is_cloud_stt() -> bool:
    return stt_backend() in ("deepgram", "whisper", "openai", "groq", "nvidia", "custom_cloud")


def is_local_stt() -> bool:
    return stt_backend() in ("parakeet", "parakeet_stream")


# Cloud STT: Deepgram
def deepgram_api_key() -> str:
    return _get("DEEPGRAM_API_KEY") or _get("CLOUD_STT_API_KEY")


def deepgram_model() -> str:
    return _get("DEEPGRAM_MODEL", "nova-3") or "nova-3"


def deepgram_language() -> str:
    return _get("DEEPGRAM_LANGUAGE", "en-US") or "en-US"


def deepgram_flux_model() -> str:
    return _get("DEEPGRAM_FLUX_MODEL", "flux-general-en") or "flux-general-en"


# Cloud STT: OpenAI Whisper / Groq / NVIDIA / Custom Cloud
def cloud_stt_provider() -> str:
    return _get("CLOUD_STT_PROVIDER", "deepgram").lower() or "deepgram"


def cloud_stt_api_key() -> str:
    return _get("CLOUD_STT_API_KEY") or _get("DEEPGRAM_API_KEY")


def cloud_stt_base_url() -> str:
    return _get("CLOUD_STT_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1"


def cloud_stt_model() -> str:
    return _get("CLOUD_STT_MODEL", "whisper-1") or "whisper-1"


def cloud_stt_language() -> str:
    return _get("CLOUD_STT_LANGUAGE", "en") or "en"


# Local STT: Parakeet
def parakeet_binary() -> str:
    return _get(
        "PARAKEET_BINARY",
        "/home/prem/projects/transcribe.cpp/build/bin/transcribe-cli",
    )


def parakeet_model() -> str:
    return _get(
        "PARAKEET_MODEL",
        "/home/prem/projects/AutoType/models/parakeet-tdt-0.6b-v2-Q4_K_M.gguf",
    )


def parakeet_stream_binary() -> str:
    return _get(
        "PARAKEET_STREAM_BINARY",
        "/home/prem/projects/parakeet.cpp/parakeet-cli",
    )


def parakeet_stream_model() -> str:
    return _get(
        "PARAKEET_STREAM_MODEL",
        "/home/prem/projects/AutoType/models/parakeet-eou-120m-q8_0.gguf",
    )


# ---------------------------------------------------------------------------
# Desktop, Audio & Mode Settings
# ---------------------------------------------------------------------------

VALID_MODES = (
    "raw", "clean", "smart",
    "professional", "casual", "email", "chat", "code",
)


def processing_mode() -> str:
    mode = _get("PROCESSING_MODE", "clean").lower()
    return mode if mode in VALID_MODES else "clean"


def command_prefix() -> str:
    return _get("COMMAND_PREFIX", "computer") or "computer"


def mic_device() -> str:
    """Preferred mic: "" = follow the system via the ALSA "pipewire" device
    (recommended: tracks Internal <-> Bluetooth switches automatically).
    Otherwise a sounddevice index ("7") or a name substring ("Buds")."""
    return _get("MIC_DEVICE", "")


def save_recordings() -> bool:
    return _get("SAVE_RECORDINGS", "false").lower() in ("1", "true", "yes")


def use_custom_prompt() -> bool:
    return _get("USE_CUSTOM_PROMPT", "false").lower() in ("1", "true", "yes")


def custom_prompt_path() -> str:
    from pathlib import Path

    custom = _get("CUSTOM_PROMPT_FILE")
    if custom:
        return custom
    return str(Path(__file__).resolve().parent / "data" / "custom_prompt.txt")


def custom_prompt() -> str:
    """User-edited cleaning prompt (empty = not set)."""
    from pathlib import Path

    try:
        text = Path(custom_prompt_path()).read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    return text
