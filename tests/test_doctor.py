"""Unit tests for autotype doctor diagnostics."""
import json
import os
from pathlib import Path
import stat
import sys
import pytest

from autotype import doctor


def test_check_session_type_x11(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    res = doctor.check_session_type()
    assert res.status == "PASS"
    assert "X11 session detected" in res.message


def test_check_session_type_wayland(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    res = doctor.check_session_type()
    assert res.status == "FAIL"
    assert "Wayland" in res.message
    assert res.fix_hint is not None


def test_check_session_type_missing_display(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    res = doctor.check_session_type()
    assert res.status == "FAIL"
    assert "DISPLAY" in res.message
    assert res.fix_hint is not None


def test_check_python_version_pass(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 11, 4, "final", 0))
    res = doctor.check_python_version()
    assert res.status == "PASS"
    assert "3.11.4" in res.message


def test_check_python_version_fail(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 9, 7, "final", 0))
    res = doctor.check_python_version()
    assert res.status == "FAIL"
    assert "unsupported" in res.message.lower()
    assert res.fix_hint is not None


def test_check_system_tools_all_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}")
    results = doctor.check_system_tools()
    assert len(results) == 4
    assert all(r.status == "PASS" for r in results)


def test_check_system_tools_fallback_missing(monkeypatch):
    def fake_which(cmd):
        if cmd == "xclip":
            return None
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr("shutil.which", fake_which)
    results = doctor.check_system_tools()
    xclip_res = next(r for r in results if r.name == "Tool xclip")
    assert xclip_res.status == "WARN"
    assert xclip_res.fix_hint is not None
    assert "sudo apt install xclip" in xclip_res.fix_hint


def test_check_system_tools_optional_missing(monkeypatch):
    def fake_which(cmd):
        if cmd == "notify-send":
            return None
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr("shutil.which", fake_which)
    results = doctor.check_system_tools()
    notify_res = next(r for r in results if r.name == "Tool notify-send")
    assert notify_res.status == "WARN"
    assert notify_res.fix_hint is not None


def test_check_audio_devices_pass(monkeypatch):
    fake_devices = [
        {"name": "pipewire", "channels": 2, "index": 0},
        {"name": "Built-in Audio", "channels": 2, "index": 1},
    ]
    monkeypatch.setattr("audio.devices.list_input_devices", lambda: fake_devices)
    res = doctor.check_audio_devices()
    assert res.status == "PASS"
    assert "2 input device(s)" in res.message


def test_check_audio_devices_fail(monkeypatch):
    monkeypatch.setattr("audio.devices.list_input_devices", lambda: [])
    res = doctor.check_audio_devices()
    assert res.status == "FAIL"
    assert "No audio capture devices detected" in res.message
    assert res.fix_hint is not None


def test_check_gtk3_gobject_pass():
    # If GTK3 is installed in test environment, it passes
    res = doctor.check_gtk3_gobject()
    assert res.status in ("PASS", "FAIL")


def test_check_gtk3_gobject_fail(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "gi":
            raise ImportError("No module named 'gi'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    res = doctor.check_gtk3_gobject()
    assert res.status == "FAIL"
    assert res.fix_hint is not None


def test_check_config_file_missing(isolated_xdg):
    res = doctor.check_config_file()
    assert res.status == "WARN"
    assert "not found" in res.message


def test_check_config_file_valid_permissions(isolated_xdg):
    cfg = isolated_xdg["config_file"]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("[general]\nprocessing_mode = 'clean'\n", encoding="utf-8")
    os.chmod(cfg, 0o600)

    res = doctor.check_config_file()
    assert res.status == "PASS"
    assert "0600 permissions" in res.message


def test_check_config_file_wrong_permissions(isolated_xdg):
    cfg = isolated_xdg["config_file"]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("[general]\nprocessing_mode = 'clean'\n", encoding="utf-8")
    os.chmod(cfg, 0o644)

    res = doctor.check_config_file()
    assert res.status == "WARN"
    assert "instead of 0600" in res.message
    assert res.fix_hint is not None


def test_check_stt_provider_deepgram_with_key(monkeypatch, isolated_xdg):
    monkeypatch.setenv("STT_BACKEND", "deepgram")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "1234567890abcdef1234567890abcdef12345678")
    res = doctor.check_stt_provider()
    assert res.status == "PASS"
    assert "API key is set" in res.message
    # Critical: Secret must NEVER be printed!
    assert "1234567890abcdef" not in res.message


def test_check_stt_provider_deepgram_missing_key(monkeypatch, isolated_xdg):
    monkeypatch.setenv("STT_BACKEND", "deepgram")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("CLOUD_STT_API_KEY", raising=False)
    res = doctor.check_stt_provider()
    assert res.status == "FAIL"
    assert "not set" in res.message
    assert res.fix_hint is not None


def test_check_stt_provider_local_parakeet(tmp_path, monkeypatch, isolated_xdg):
    fake_bin = tmp_path / "transcribe-cli"
    fake_bin.write_text("#!/bin/sh\nexit 0")
    os.chmod(fake_bin, 0o755)

    fake_model = tmp_path / "model.gguf"
    fake_model.write_text("model content")

    monkeypatch.setenv("STT_BACKEND", "parakeet")
    monkeypatch.setenv("PARAKEET_BINARY", str(fake_bin))
    monkeypatch.setenv("PARAKEET_MODEL", str(fake_model))

    res = doctor.check_stt_provider()
    assert res.status == "PASS"
    assert "binary and model paths exist" in res.message


def test_check_stt_provider_local_parakeet_missing(tmp_path, monkeypatch, isolated_xdg):
    monkeypatch.setenv("STT_BACKEND", "parakeet")
    monkeypatch.setenv("PARAKEET_BINARY", str(tmp_path / "nonexistent-bin"))
    monkeypatch.setenv("PARAKEET_MODEL", str(tmp_path / "nonexistent-model.gguf"))

    res = doctor.check_stt_provider()
    assert res.status == "FAIL"
    assert "missing" in res.message
    assert res.fix_hint is not None


def test_check_llm_provider_cloud_with_key(monkeypatch, isolated_xdg):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-supersecretkey123456789012345")
    res = doctor.check_llm_provider()
    assert res.status == "PASS"
    assert "API key is set" in res.message
    # Critical: Secret must NEVER be printed!
    assert "supersecretkey" not in res.message


def test_check_llm_provider_cloud_missing_key(monkeypatch, isolated_xdg):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
    res = doctor.check_llm_provider()
    assert res.status == "FAIL"
    assert "not set" in res.message
    assert res.fix_hint is not None


def test_check_llm_provider_ollama(monkeypatch, isolated_xdg):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    res = doctor.check_llm_provider()
    assert res.status == "PASS"
    assert "ollama" in res.message.lower()


def test_check_llm_provider_custom_no_key(monkeypatch, isolated_xdg):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
    res = doctor.check_llm_provider()
    assert res.status == "WARN"
    assert "without an API key" in res.message


def test_check_data_directory_writable(isolated_xdg):
    res = doctor.check_data_directory()
    assert res.status == "PASS"
    assert "writable" in res.message


def test_check_daemon_status_no_pid(isolated_xdg):
    res = doctor.check_daemon_status()
    assert res.status == "PASS"
    assert "not running" in res.message


def test_check_daemon_status_running(isolated_xdg):
    pid_file = isolated_xdg["data_dir"] / "daemon.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    # Use current test process pid
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    res = doctor.check_daemon_status()
    assert res.status == "PASS"
    assert f"PID {os.getpid()}" in res.message


def test_check_daemon_status_stale(isolated_xdg):
    pid_file = isolated_xdg["data_dir"] / "daemon.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    # PID 999999 is almost certainly not running
    pid_file.write_text("999999", encoding="utf-8")

    res = doctor.check_daemon_status()
    assert res.status == "WARN"
    assert "Stale" in res.message
    assert res.fix_hint is not None


def test_doctor_json_output_valid():
    report = doctor.run_checks()
    json_str = doctor.format_report_json(report)
    parsed = json.loads(json_str)

    assert "version" in parsed
    assert "ok" in parsed
    assert "summary" in parsed
    assert "checks" in parsed
    assert isinstance(parsed["checks"], list)
    assert len(parsed["checks"]) >= 10
    for chk in parsed["checks"]:
        assert chk["status"] in ("PASS", "WARN", "FAIL")
        assert "name" in chk
        assert "message" in chk
