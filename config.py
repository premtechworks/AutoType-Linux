"""Central config. All secrets and model names come from .env — nothing hard-coded."""
import os

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing {name} in .env. Copy .env.example to .env and fill it in."
        )
    return value


def deepgram_api_key() -> str:
    return _required("DEEPGRAM_API_KEY")


def deepgram_model() -> str:
    return os.getenv("DEEPGRAM_MODEL", "nova-3").strip() or "nova-3"


def deepgram_language() -> str:
    return os.getenv("DEEPGRAM_LANGUAGE", "en-US").strip() or "en-US"


def deepgram_flux_model() -> str:
    return os.getenv("DEEPGRAM_FLUX_MODEL", "flux-general-en").strip() or "flux-general-en"


def omniroute_base_url() -> str:
    return _required("OMNIROUTE_BASE_URL").rstrip("/")


def omniroute_api_key() -> str:
    return _required("OMNIROUTE_API_KEY")


def omniroute_model() -> str:
    return os.getenv("OMNIROUTE_MODEL", "auto").strip() or "auto"


def stt_backend() -> str:
    return os.getenv("STT_BACKEND", "deepgram").strip().lower() or "deepgram"


def save_recordings() -> bool:
    return os.getenv("SAVE_RECORDINGS", "false").strip().lower() in (
        "1", "true", "yes",
    )


def parakeet_stream_binary() -> str:
    return (
        os.getenv(
            "PARAKEET_STREAM_BINARY",
            "/home/prem/projects/parakeet.cpp/parakeet-cli",
        ).strip()
    )


def parakeet_stream_model() -> str:
    return (
        os.getenv(
            "PARAKEET_STREAM_MODEL",
            "/home/prem/projects/AutoType/models/parakeet-eou-120m-q8_0.gguf",
        ).strip()
    )


VALID_MODES = (
    "raw", "clean", "smart",
    "professional", "casual", "email", "chat", "code",
)


def processing_mode() -> str:
    mode = os.getenv("PROCESSING_MODE", "clean").strip().lower()
    return mode if mode in VALID_MODES else "clean"


def command_prefix() -> str:
    return os.getenv("COMMAND_PREFIX", "computer").strip() or "computer"


def mic_device() -> str:
    """Preferred mic: "" = follow the system via the ALSA "pipewire" device
    (recommended: tracks Internal <-> Bluetooth switches automatically).
    Otherwise a sounddevice index ("7") or a name substring ("Buds")."""
    return os.getenv("MIC_DEVICE", "").strip()


def use_custom_prompt() -> bool:
    return os.getenv("USE_CUSTOM_PROMPT", "false").strip().lower() in (
        "1", "true", "yes",
    )


def custom_prompt_path() -> str:
    from pathlib import Path

    custom = os.getenv("CUSTOM_PROMPT_FILE", "").strip()
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


def cleaning_temperature() -> float:
    try:
        return float(os.getenv("CLEANING_TEMPERATURE", "0.1").strip() or 0.1)
    except ValueError:
        return 0.1
