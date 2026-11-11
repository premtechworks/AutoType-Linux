"""Unit tests for desktop/clipboard.py (GTK3 clipboard with xclip fallback)."""
from unittest.mock import MagicMock, patch
import pytest

from desktop import clipboard


def test_copy_and_get_clipboard_text():
    """Verify copying text to clipboard and reading it back."""
    test_text = "AutoType Test Clipboard String 123"
    clipboard.copy_to_clipboard(test_text)
    val = clipboard.get_clipboard()
    assert val == test_text


def test_restore_clipboard_text():
    """Verify restoring previous text into the clipboard."""
    initial = "Initial Clipboard Content"
    clipboard.copy_to_clipboard(initial)
    assert clipboard.get_clipboard() == initial

    # Dictate new text
    clipboard.copy_to_clipboard("Dictated Transcript")
    assert clipboard.get_clipboard() == "Dictated Transcript"

    # Restore initial
    clipboard.restore_clipboard(initial)
    assert clipboard.get_clipboard() == initial


def test_restore_clipboard_none():
    """Verify restoring None (empty clipboard) clears the clipboard."""
    clipboard.copy_to_clipboard("Some text before clear")
    clipboard.restore_clipboard(None)
    val = clipboard.get_clipboard()
    assert val is None or val == ""


def test_restore_clipboard_bytes():
    """Verify restoring bytes (backwards compatibility with xclip bytes)."""
    raw_bytes = b"Raw bytes restored"
    clipboard.restore_clipboard(raw_bytes)
    assert clipboard.get_clipboard() == "Raw bytes restored"


def test_non_text_clipboard_resilience():
    """Verify non-text clipboard (e.g. image object) does not crash get or restore."""
    # Mock an image object with get_width
    fake_image = MagicMock()
    fake_image.get_width.return_value = 100

    # Should not raise any exception
    clipboard.restore_clipboard(fake_image)

    # Calling restore with arbitrary object should not crash
    clipboard.restore_clipboard(object())


def test_fallback_to_xclip_when_gtk_unavailable(monkeypatch):
    """Verify xclip fallback is invoked if GTK clipboard is unavailable."""
    monkeypatch.setattr(clipboard, "_get_gtk_clipboard", lambda: None)

    runs = []

    def fake_run(cmd, *args, **kwargs):
        runs.append(cmd)
        mock_res = MagicMock()
        mock_res.stdout = b"Fallback from xclip"
        return mock_res

    monkeypatch.setattr("subprocess.run", fake_run)

    # 1. get_clipboard
    text = clipboard.get_clipboard()
    assert text == b"Fallback from xclip"
    assert any("xclip" in cmd[0] for cmd in runs)

    # 2. copy_to_clipboard
    clipboard.copy_to_clipboard("Hello fallback")
    assert any(cmd == ["xclip", "-selection", "clipboard"] for cmd in runs)

    # 3. restore_clipboard
    clipboard.restore_clipboard(b"Restore fallback")
    assert any(cmd == ["xclip", "-selection", "clipboard"] for cmd in runs)


def test_insert_text_restores_clipboard_by_default(monkeypatch):
    """Default insert_text pastes, then puts the previous clipboard back."""
    calls = []
    monkeypatch.setattr(clipboard, "get_clipboard", lambda: "previous text")
    monkeypatch.setattr(clipboard, "copy_to_clipboard", lambda t: calls.append(("copy", t)))
    monkeypatch.setattr(clipboard, "paste_into_active_window", lambda: calls.append(("paste", None)))
    monkeypatch.setattr(clipboard, "restore_clipboard", lambda d: calls.append(("restore", d)))
    monkeypatch.setattr(clipboard.time, "sleep", lambda _s: None)

    clipboard.insert_text("dictated text")

    assert ("copy", "dictated text") in calls
    assert ("paste", None) in calls
    assert ("restore", "previous text") in calls


def test_insert_text_keeps_text_when_requested(monkeypatch):
    """keep_in_clipboard=True leaves the dictated text on the clipboard."""
    calls = []
    monkeypatch.setattr(clipboard, "get_clipboard", lambda: "previous text")
    monkeypatch.setattr(clipboard, "copy_to_clipboard", lambda t: calls.append(("copy", t)))
    monkeypatch.setattr(clipboard, "paste_into_active_window", lambda: calls.append(("paste", None)))
    monkeypatch.setattr(clipboard, "restore_clipboard", lambda d: calls.append(("restore", d)))
    monkeypatch.setattr(clipboard.time, "sleep", lambda _s: None)

    clipboard.insert_text("dictated text", keep_in_clipboard=True)

    assert ("copy", "dictated text") in calls
    assert ("paste", None) in calls
    assert not any(call[0] == "restore" for call in calls)


def test_get_selected_text_fallback_to_xclip(monkeypatch):
    """Verify get_selected_text falls back to xclip primary when GTK fails."""
    monkeypatch.setattr(clipboard, "_get_gtk_primary", lambda: None)

    def fake_run(cmd, *args, **kwargs):
        mock_res = MagicMock()
        mock_res.stdout = b"Highlighted text\n"
        return mock_res

    monkeypatch.setattr("subprocess.run", fake_run)

    res = clipboard.get_selected_text()
    assert res == "Highlighted text"
