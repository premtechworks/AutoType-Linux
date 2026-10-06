"""Active-window detection via xdotool (X11)."""
import subprocess

TERMINAL_HINTS = (
    "terminal", "xterm", "konsole", "terminator",
    "alacritty", "kitty", "gnome-terminal",
    "xfce4-terminal", "bash", "zsh", "fish",
)


def active_window_title() -> str:
    result = subprocess.run(
        ["xdotool", "getactivewindow", "getwindowname"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def active_window_class() -> str:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowclassname"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def is_terminal_window() -> bool:
    haystack = f"{active_window_title()} {active_window_class()}".lower()
    return any(hint in haystack for hint in TERMINAL_HINTS)
