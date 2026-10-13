"""Unit tests for desktop/notifications.py (optional notify-send with debug logging)."""
import logging
from unittest.mock import MagicMock, patch
import pytest

from desktop import notifications


def test_notify_when_notify_send_present(monkeypatch):
    """Verify notification is dispatched via subprocess when notify-send exists."""
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/notify-send" if cmd == "notify-send" else None)

    runs = []

    def fake_run(cmd, *args, **kwargs):
        runs.append(cmd)
        return MagicMock()

    monkeypatch.setattr("subprocess.run", fake_run)

    notifications.notify("Test Title", "Test Message")
    assert len(runs) == 1
    assert runs[0] == ["notify-send", "Test Title", "Test Message", "--app-name", "AutoType"]


def test_notify_when_notify_send_absent_skips_and_logs(monkeypatch, caplog):
    """Verify notification is silently skipped and logged at DEBUG when notify-send is absent."""
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    runs = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: runs.append(args))

    with caplog.at_level(logging.DEBUG, logger="autotype.notifications"):
        notifications.notify("Important Title", "Important Message")

    # subprocess should not be invoked
    assert len(runs) == 0

    # DEBUG message must be logged
    assert any("notify-send not found; skipping notification" in record.message for record in caplog.records)
    assert any("Important Title - Important Message" in record.message for record in caplog.records)
