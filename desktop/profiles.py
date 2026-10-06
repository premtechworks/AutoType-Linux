"""Application profiles for Smart mode: map the focused window to a prompt style."""
import json
from pathlib import Path

from .windows import active_window_class, active_window_title

# profile -> keyword hints matched against "title + class" (lowercase)
PROFILE_HINTS: dict[str, tuple[str, ...]] = {
    "code": (
        "code", "vscode", "vim", "neovim", "sublime", "pycharm",
        "intellij", "emacs", "geany", "mousepad", "terminal",
        "xterm", "konsole", "terminator", "alacritty", "kitty",
        "gnome-terminal", "xfce4-terminal", "bash", "zsh", "fish",
    ),
    "email": (
        "thunderbird", "outlook", "gmail", "protonmail", "tutanota",
        "evolution", "kmail", "claws",
    ),
    "chat": (
        "telegram", "whatsapp", "discord", "slack", "signal",
        "teams", "messenger",
    ),
}

PROFILE_LABELS = {
    "code": "a code editor or terminal (preserve identifiers, be literal)",
    "email": "an email client (polite, structured prose)",
    "chat": "a chat app (casual, concise)",
    "prose": "a general application (normal prose)",
}

# Smart-mode mapping: app profile -> concrete LLM style mode.
PROFILE_TO_MODE = {
    "code": "code",
    "email": "email",
    "chat": "chat",
    "prose": "clean",
}


def profile_to_mode(profile: str) -> str:
    """Map a detected app profile to its default style mode."""
    return PROFILE_TO_MODE.get(profile, "clean")

OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "profiles.json"


def _custom_hints() -> dict[str, tuple[str, ...]]:
    """User overrides from data/profiles.json: {"overrides": {profile: [hints]}}."""
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        overrides = data.get("overrides", {}) if isinstance(data, dict) else {}
        return {
            str(profile): tuple(h.lower() for h in hints if isinstance(h, str))
            for profile, hints in overrides.items()
            if isinstance(hints, list) and profile in PROFILE_LABELS
        }
    except Exception:
        return {}


def detect_profile() -> tuple[str, str]:
    """Return (profile, app_label). Never raises — falls back to prose."""
    try:
        haystack = f"{active_window_title()} {active_window_class()}".lower()
    except Exception:
        return "prose", "an unknown application"
    hints_map = {**PROFILE_HINTS, **_custom_hints()}
    for profile, hints in hints_map.items():
        if any(hint in haystack for hint in hints):
            return profile, PROFILE_LABELS[profile]
    return "prose", PROFILE_LABELS["prose"]
