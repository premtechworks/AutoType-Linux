"""Active-window detection via python-xlib with automatic xdotool fallback (X11)."""
from __future__ import annotations

import subprocess

TERMINAL_HINTS = (
    "terminal", "xterm", "konsole", "terminator",
    "alacritty", "kitty", "gnome-terminal",
    "xfce4-terminal", "bash", "zsh", "fish",
)


def _xlib_active_window_info() -> tuple[str, str] | None:
    """Query active window title and class using python-xlib over X11 connection.

    Returns (title, class_str) or None if Xlib is unavailable or window cannot be resolved.
    """
    try:
        from Xlib import X, display
        d = display.Display()
        root = d.screen().root
        net_active = d.intern_atom("_NET_ACTIVE_WINDOW")
        prop = root.get_full_property(net_active, X.AnyPropertyType)
        if not prop or not prop.value:
            d.close()
            return None
        win_id = prop.value[0]
        if not win_id:
            d.close()
            return None
        win = d.create_resource_object("window", win_id)

        # 1. Window title: try _NET_WM_NAME (UTF8_STRING), then WM_NAME
        title = ""
        try:
            net_wm_name = d.intern_atom("_NET_WM_NAME")
            utf8_string = d.intern_atom("UTF8_STRING")
            name_prop = win.get_full_property(net_wm_name, utf8_string)
            if name_prop and name_prop.value:
                val = name_prop.value
                title = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val)
            else:
                title = win.get_wm_name() or ""
        except Exception:
            title = ""

        # 2. Window class: WM_CLASS (tuple of instance, class_name)
        cls_str = ""
        try:
            wm_class = win.get_wm_class()
            if wm_class:
                if isinstance(wm_class, (tuple, list)):
                    cls_str = " ".join(str(c) for c in wm_class)
                else:
                    cls_str = str(wm_class)
        except Exception:
            cls_str = ""

        d.close()
        return title.strip(), cls_str.strip()
    except Exception:
        return None


def active_window_title() -> str:
    """Return the active window's title string."""
    info = _xlib_active_window_info()
    if info is not None:
        return info[0]

    # Fallback to xdotool
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def active_window_class() -> str:
    """Return the active window's WM_CLASS string."""
    info = _xlib_active_window_info()
    if info is not None:
        return info[1]

    # Fallback to xdotool
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

