"""Unit tests for desktop/windows.py (python-xlib window detection with xdotool fallback)
and style classification in desktop/profiles.py.
"""
from unittest.mock import MagicMock, patch
import pytest

from desktop import windows, clipboard
from desktop.profiles import detect_profile


def test_active_window_title_and_class_xlib():
    """Verify python-xlib returns active window title and class."""
    # Under an active X11 session, python-xlib should query without raising
    title = windows.active_window_title()
    cls = windows.active_window_class()
    assert isinstance(title, str)
    assert isinstance(cls, str)


def test_active_window_fallback_to_xdotool(monkeypatch):
    """Verify fallback to xdotool if python-xlib returns None."""
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: None)

    runs = []

    def fake_run(cmd, *args, **kwargs):
        runs.append(cmd)
        mock_res = MagicMock()
        if "getwindowname" in cmd:
            mock_res.stdout = "Test Window Name\n"
        elif "getwindowclassname" in cmd:
            mock_res.stdout = "TestWindowClass\n"
        return mock_res

    monkeypatch.setattr("subprocess.run", fake_run)

    title = windows.active_window_title()
    assert title == "Test Window Name"
    assert any("getwindowname" in cmd for cmd in runs)

    cls = windows.active_window_class()
    assert cls == "TestWindowClass"
    assert any("getwindowclassname" in cmd for cmd in runs)


def test_is_terminal_window_detection(monkeypatch):
    """Verify terminal detection across various terminal names."""
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("user@host: ~", "xfce4-terminal"))
    assert windows.is_terminal_window() is True

    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("bash", "xterm"))
    assert windows.is_terminal_window() is True

    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("Untitled - Google Docs", "google-chrome"))
    assert windows.is_terminal_window() is False


def test_style_classification_code(monkeypatch):
    """Verify 'code' style profile detection for editors and terminals."""
    # VS Code
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("app.py - AutoType - Visual Studio Code", "code"))
    profile, label = detect_profile()
    assert profile == "code"

    # Terminal
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("prem@linux: ~/projects", "xfce4-terminal"))
    profile, label = detect_profile()
    assert profile == "code"


def test_style_classification_email(monkeypatch):
    """Verify 'email' style profile detection for email clients."""
    # Thunderbird
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("Inbox - Mozilla Thunderbird", "thunderbird"))
    profile, label = detect_profile()
    assert profile == "email"

    # Gmail in browser title
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("Gmail - Inbox (1) - Chromium", "chromium"))
    profile, label = detect_profile()
    assert profile == "email"


def test_style_classification_chat(monkeypatch):
    """Verify 'chat' style profile detection for messaging apps."""
    # Slack
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("Slack | general | Workspace", "slack"))
    profile, label = detect_profile()
    assert profile == "chat"

    # Telegram
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("Telegram", "telegram-desktop"))
    profile, label = detect_profile()
    assert profile == "chat"


def test_style_classification_prose(monkeypatch):
    """Verify 'prose' style profile detection for general apps."""
    monkeypatch.setattr(windows, "_xlib_active_window_info", lambda: ("Document 1 - LibreOffice Writer", "libreoffice-writer"))
    profile, label = detect_profile()
    assert profile == "prose"


def test_paste_into_active_window_fallback_to_xdotool(monkeypatch):
    """Verify paste_into_active_window falls back to xdotool when xlib paste fails."""
    monkeypatch.setattr(clipboard, "_xlib_paste", lambda keys: False)
    monkeypatch.setattr(clipboard, "is_terminal_window", lambda: False)

    runs = []

    def fake_run(cmd, *args, **kwargs):
        runs.append(cmd)
        return MagicMock()

    monkeypatch.setattr("subprocess.run", fake_run)

    clipboard.paste_into_active_window()
    assert any(cmd == ["xdotool", "key", "--clearmodifiers", "ctrl+v"] for cmd in runs)
