"""Clipboard + paste. Saves/restores the user's prior clipboard around the paste."""
from __future__ import annotations

import subprocess
import time
from typing import Any

from .windows import is_terminal_window

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gtk
except Exception:
    Gtk = None
    Gdk = None


def _get_gtk_clipboard():
    if Gtk is None or Gdk is None:
        return None
    try:
        return Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    except Exception:
        return None


def _get_gtk_primary():
    if Gtk is None or Gdk is None:
        return None
    try:
        return Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
    except Exception:
        return None


def get_clipboard() -> Any:
    clip = _get_gtk_clipboard()
    if clip is not None:
        try:
            if clip.wait_is_text_available():
                return clip.wait_for_text()
            if hasattr(clip, "wait_is_image_available") and clip.wait_is_image_available():
                return clip.wait_for_image()
            return None
        except Exception:
            pass
    # Fallback to xclip if GTK is unavailable or fails
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, check=True,
        )
        return result.stdout
    except Exception:
        return None


def copy_to_clipboard(text: str) -> None:
    clip = _get_gtk_clipboard()
    if clip is not None:
        try:
            clip.set_text(text, -1)
            clip.store()
            return
        except Exception:
            pass
    # Fallback to xclip
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text.encode("utf-8"), check=True,
    )


def restore_clipboard(data: Any) -> None:
    clip = _get_gtk_clipboard()
    if clip is not None:
        try:
            if data is None:
                clip.clear()
            elif isinstance(data, (str, bytes)):
                text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
                clip.set_text(text, -1)
                clip.store()
            elif hasattr(data, "get_width"):  # GdkPixbuf image object
                clip.set_image(data)
                clip.store()
            else:
                clip.clear()
            return
        except Exception:
            pass
    # Fallback to xclip
    if data is None:
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-i", "/dev/null"],
            check=False,
        )
        return
    if isinstance(data, (str, bytes)):
        raw = data if isinstance(data, bytes) else str(data).encode("utf-8")
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=raw, check=False,
        )


def get_selected_text() -> str:
    """Best-effort read of the current X primary selection (highlight).

    Used for selected-text transforms ("make this sound more professional").
    Returns "" when nothing is selected or xclip/GTK primary is unavailable —
    callers must treat that as 'no selection' and dictate fresh text instead.
    """
    primary = _get_gtk_primary()
    if primary is not None:
        try:
            if primary.wait_is_text_available():
                text = primary.wait_for_text()
                if text:
                    return text.strip()
            return ""
        except Exception:
            pass
    # Fallback to xclip
    try:
        result = subprocess.run(
            ["xclip", "-selection", "primary", "-o"],
            capture_output=True, check=True, timeout=2,
        )
        return result.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _xlib_paste(keys: str) -> bool:
    """Synthesize paste keystrokes using XTest extension via python-xlib.

    Returns True if synthesized successfully, False otherwise.
    """
    try:
        from Xlib import X, display
        from Xlib.ext import xtest
        import Xlib.XK as XK

        d = display.Display()
        if not d.has_extension("XTEST"):
            d.close()
            return False

        ctrl_kc = d.keysym_to_keycode(XK.XK_Control_L)
        shift_kc = d.keysym_to_keycode(XK.XK_Shift_L)
        v_kc = d.keysym_to_keycode(XK.string_to_keysym("v"))

        if not ctrl_kc or not v_kc:
            d.close()
            return False

        is_shift = "shift" in keys.lower()

        # Press modifiers and V
        xtest.fake_input(d, X.KeyPress, ctrl_kc)
        if is_shift:
            xtest.fake_input(d, X.KeyPress, shift_kc)
        xtest.fake_input(d, X.KeyPress, v_kc)

        # Release V and modifiers
        xtest.fake_input(d, X.KeyRelease, v_kc)
        if is_shift:
            xtest.fake_input(d, X.KeyRelease, shift_kc)
        xtest.fake_input(d, X.KeyRelease, ctrl_kc)

        d.sync()
        d.close()
        return True
    except Exception:
        return False


def paste_into_active_window() -> None:
    # Terminals need Ctrl+Shift+V; GUI apps need Ctrl+V.
    try:
        terminal = is_terminal_window()
    except Exception:
        terminal = False
    keys = "ctrl+shift+v" if terminal else "ctrl+v"
    time.sleep(0.15)  # let the clipboard settle

    # 1. Try python-xlib XTest synthetic keystrokes first (pure Python, sandbox-friendly)
    if _xlib_paste(keys):
        return

    # 2. Fallback to xdotool
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
