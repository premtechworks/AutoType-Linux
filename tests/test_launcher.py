"""Unit tests for autotype/launcher.py (start-on-demand and already-running check)."""
import os
import subprocess

import pytest

from autotype import launcher


def _write_pid(isolated_xdg, pid) -> None:
    data_dir = isolated_xdg["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "daemon.pid").write_text(str(pid))


def test_running_pid_none_without_pid_file(isolated_xdg):
    assert launcher.running_pid() is None


def test_running_pid_ignores_invalid_pid_file(isolated_xdg):
    _write_pid(isolated_xdg, "not-a-pid")
    assert launcher.running_pid() is None


def test_running_pid_detects_live_daemon(isolated_xdg, monkeypatch):
    _write_pid(isolated_xdg, os.getpid())
    monkeypatch.setattr(launcher, "_looks_like_daemon", lambda pid: True)
    assert launcher.running_pid() == os.getpid()


def test_running_pid_removes_stale_pid_file(isolated_xdg):
    proc = subprocess.Popen(["true"])
    proc.wait()
    _write_pid(isolated_xdg, proc.pid)

    assert launcher.running_pid() is None
    assert not (isolated_xdg["data_dir"] / "daemon.pid").exists()


def test_running_pid_rejects_unrelated_process(isolated_xdg, monkeypatch):
    _write_pid(isolated_xdg, os.getpid())
    monkeypatch.setattr(launcher, "_looks_like_daemon", lambda pid: False)

    assert launcher.running_pid() is None
    assert not (isolated_xdg["data_dir"] / "daemon.pid").exists()


def test_run_reports_already_running(isolated_xdg, monkeypatch):
    messages = []
    spawned = []
    monkeypatch.setattr(launcher, "running_pid", lambda: 4242)
    monkeypatch.setattr(launcher, "show_message", lambda text, **kw: messages.append(text))
    monkeypatch.setattr(launcher, "_spawn", lambda cmd: spawned.append(cmd))

    assert launcher.run() == 0
    assert spawned == []
    assert messages and "already running" in messages[0].lower()


def test_run_starts_daemon_then_settings(isolated_xdg, monkeypatch):
    spawned = []
    monkeypatch.setattr(launcher, "running_pid", lambda: None)
    monkeypatch.setattr(launcher, "show_message", lambda *a, **k: None)
    monkeypatch.setattr(launcher, "_spawn", lambda cmd: spawned.append(cmd) or object())
    monkeypatch.setattr(launcher, "_wait_for_daemon", lambda proc, timeout=10.0: True)

    assert launcher.run() == 0
    assert spawned == [["daemon"], ["settings"]]


def test_run_forwards_debug_flag(isolated_xdg, monkeypatch):
    spawned = []
    monkeypatch.setattr(launcher, "running_pid", lambda: None)
    monkeypatch.setattr(launcher, "show_message", lambda *a, **k: None)
    monkeypatch.setattr(launcher, "_spawn", lambda cmd: spawned.append(cmd) or object())
    monkeypatch.setattr(launcher, "_wait_for_daemon", lambda proc, timeout=10.0: True)

    launcher.run(debug=True, open_settings=False)
    assert spawned == [["daemon", "--debug"]]


def test_daemon_main_refuses_second_instance(isolated_xdg, monkeypatch):
    from app import main

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(launcher, "running_pid", lambda: 4242)

    notified = []
    monkeypatch.setattr("app.notify", lambda app_name, msg: notified.append((app_name, msg)))

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert notified and "already running (PID 4242)" in notified[0][1]


def test_run_reports_start_failure(isolated_xdg, monkeypatch):
    messages = []
    monkeypatch.setattr(launcher, "running_pid", lambda: None)
    monkeypatch.setattr(launcher, "show_message", lambda text, **kw: messages.append(text))
    monkeypatch.setattr(launcher, "_spawn", lambda cmd: object())
    monkeypatch.setattr(launcher, "_wait_for_daemon", lambda proc, timeout=10.0: False)

    assert launcher.run() == 1
    assert messages and "failed to start" in messages[0].lower()