"""Clipboard + paste. Saves/restores the user's prior clipboard around the paste."""
import subprocess
import time

from .windows import is_terminal_window


def get_clipboard() -> bytes | None:
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None  # empty clipboard


def copy_to_clipboard(text: str) -> None:
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text.encode("utf-8"), check=True,
    )


def restore_clipboard(data: bytes | None) -> None:
    if data is None:
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-i", "/dev/null"],
            check=False,
        )
        return
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=data, check=False,
    )


def get_selected_text() -> str:
    """Best-effort read of the current X primary selection (highlight).

    Used for selected-text transforms ("make this sound more professional").
    Returns "" when nothing is selected or xclip is unavailable — callers
    must treat that as 'no selection' and dictate fresh text instead.
    """
    try:
        result = subprocess.run(
            ["xclip", "-selection", "primary", "-o"],
            capture_output=True, check=True, timeout=2,
        )
        return result.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def paste_into_active_window() -> None:
    # Terminals need Ctrl+Shift+V; GUI apps need Ctrl+V.
    try:
        terminal = is_terminal_window()
    except Exception:
        terminal = False
    keys = "ctrl+shift+v" if terminal else "ctrl+v"
    time.sleep(0.15)  # let the clipboard settle
    subprocess.run(
        ["xdotool", "key", "--clearmodifiers", keys],
        check=True,
    )


def insert_text(text: str) -> None:
    """Copy, paste, then restore the user's previous clipboard contents."""
    previous = get_clipboard()
    copy_to_clipboard(text)
    try:
        paste_into_active_window()
    finally:
        time.sleep(0.4)  # let the target app consume the paste first
        try:
            restore_clipboard(previous)
        except Exception:
            pass
