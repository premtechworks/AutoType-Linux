"""On-demand launcher: start the daemon and open settings, or report a running instance.

Powers `autotype launch`, the `autotype-launch.sh` helper and the desktop
entry. Double-clicking AutoType starts the background service and the settings
window; if a daemon is already running it shows an "already running" dialog
instead of starting a second instance (two daemons would fight over the
Right-Alt hotkey).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time

from autotype import paths

APP_NAME = "AutoType"
_START_TIMEOUT = 10.0
_POLL_INTERVAL = 0.1

log = logging.getLogger("autotype.launcher")


def pid_file():
    """Path of the daemon pid file (written by app.main())."""
    return paths.get_data_dir() / "daemon.pid"


def _remove_stale_pid() -> None:
    try:
        pid_file().unlink(missing_ok=True)
    except Exception:
        pass


def _pid_command_line(pid: int) -> str | None:
    """Return the process command line, None when /proc cannot be inspected."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except FileNotFoundError:
        return ""  # process is gone
    except Exception:
        return None


def _looks_like_daemon(pid: int) -> bool:
    """Guard against PID reuse: only trust pids that look like AutoType."""
    cmd = _pid_command_line(pid)
    if cmd is None:
        return True  # cannot inspect (/proc restricted): assume it is alive
    if not cmd:
        return False
    return "autotype" in cmd or "app.py" in cmd


def running_pid() -> int | None:
    """PID of the live AutoType daemon, or None. Stale pid files are removed."""
    try:
        pid = int(pid_file().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid <= 0:
        _remove_stale_pid()
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        _remove_stale_pid()
        return None
    except PermissionError:
        return pid  # alive, owned by another user
    if not _looks_like_daemon(pid):
        _remove_stale_pid()
        return None
    return pid


def _spawn(subcommand: list[str]) -> subprocess.Popen:
    """Run `autotype <subcommand>` detached from this process."""
    env = os.environ.copy()
    cwd = None
    root = paths.find_repo_root()
    if root is not None:
        # A checkout is not necessarily on sys.path for the child interpreter.
        cwd = str(root)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + (os.pathsep + existing if existing else "")
    return subprocess.Popen(
        [sys.executable, "-m", "autotype.cli", *subcommand],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=cwd,
        env=env,
    )


def show_message(text: str, title: str = APP_NAME, warning: bool = False) -> None:
    """Show a dialog through GTK, falling back to zenity and then stderr."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.WARNING if warning else Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        )
        dialog.set_title(title)
        dialog.run()
        dialog.destroy()
        return
    except Exception:
        pass
    if shutil.which("zenity"):
        try:
            subprocess.run(
                ["zenity", "--warning" if warning else "--info",
                 "--title", title, "--text", text, "--width", "360"],
                check=False,
            )
            return
        except Exception:
            pass
    print(f"{title}: {text}", file=sys.stderr)


def _wait_for_daemon(proc: subprocess.Popen, timeout: float = _START_TIMEOUT) -> bool:
    """Wait until the daemon writes its pid file, or until the process dies."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if running_pid() is not None:
            return True
        if proc.poll() is not None:
            return False
        time.sleep(_POLL_INTERVAL)
    return running_pid() is not None


def run(debug: bool = False, open_settings: bool = True) -> int:
    """Start the daemon when needed and open the settings window.

    Returns 0 on success (including the already-running case), 1 on failure.
    """
    pid = running_pid()
    if pid is not None:
        show_message(f"{APP_NAME} is already running (PID {pid}).", warning=True)
        return 0

    daemon = _spawn(["daemon"] + (["--debug"] if debug else []))
    if not _wait_for_daemon(daemon):
        show_message(
            f"{APP_NAME} failed to start. Run 'autotype daemon --debug' in a "
            "terminal to see the error.",
            warning=True,
        )
        return 1

    log.info("Started %s daemon (PID %s).", APP_NAME, running_pid())
    if open_settings:
        try:
            _spawn(["settings"])
        except Exception as exc:
            log.warning("Failed to open settings: %s", exc)
            show_message(
                f"The daemon started, but the settings window failed to open: {exc}",
                warning=True,
            )
            return 1
    return 0