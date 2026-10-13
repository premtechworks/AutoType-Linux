"""Desktop notifications via libnotify (optional)."""
from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger("autotype.notifications")

APP_NAME = "AutoType"


def notify(title: str, message: str) -> None:
    """Send a desktop notification via notify-send if available.

    If notify-send is absent, silently logs a debug message and returns.
    """
    if not shutil.which("notify-send"):
        log.debug("notify-send not found; skipping notification: %s - %s", title, message)
        return

    try:
        subprocess.run(
            ["notify-send", title, message, "--app-name", APP_NAME],
            check=False,
        )
    except Exception as exc:
        log.debug("Failed to dispatch notification via notify-send: %s", exc)

