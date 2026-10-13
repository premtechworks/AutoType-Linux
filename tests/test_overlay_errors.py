"""Unit tests for actionable overlay error states."""
import os
from unittest.mock import MagicMock, patch
import pytest

from autotype.errors import format_actionable_error


# =============================================================================
# 1. format_actionable_error unit tests
# =============================================================================

def test_missing_deepgram_api_key():
    err = "Missing DEEPGRAM_API_KEY in .env."
    res = format_actionable_error(err)
    assert res == "Missing Deepgram API key (Settings → Speech)"


def test_missing_cloud_stt_api_key():
    err = "Missing API key for Cloud STT. Configure it in Settings → Speech."
    res = format_actionable_error(err)
    assert res == "Missing Cloud STT API key (Settings → Speech)"


def test_invalid_stt_api_key():
    err = "Deepgram request failed: 401 Client Error: Unauthorized for url"
    res = format_actionable_error(err, context="stt")
    assert res == "Invalid STT API key (Settings → Speech)"


def test_missing_llm_api_key():
    err = "Missing Anthropic API key. Add it in Settings → Cleaning."
    res = format_actionable_error(err, context="llm")
    assert res == "Missing LLM API key (Settings → Cleaning)"


def test_invalid_llm_api_key():
    err = "Error code: 401 - {'error': {'message': 'Incorrect API key provided'}}"
    res = format_actionable_error(err, context="llm")
    assert res == "Invalid LLM API key (Settings → Cleaning)"


def test_local_binary_not_found():
    err = "Parakeet binary not found at /usr/local/bin/parakeet-cli"
    res = format_actionable_error(err)
    assert res == "Local STT binary or model not found (Settings → Speech)"


def test_local_model_not_found():
    err = "Parakeet model not found at ~/.local/share/autotype/models/fastconformer.nemo"
    res = format_actionable_error(err)
    assert res == "Local STT binary or model not found (Settings → Speech)"


def test_streaming_binary_not_found():
    err = "Streaming binary not found at /usr/local/bin/parakeet-stream"
    res = format_actionable_error(err)
    assert res == "Local STT binary or model not found (Settings → Speech)"


def test_no_microphone_detected():
    err = "No microphone detected"
    res = format_actionable_error(err, context="mic")
    assert res == "No microphone detected (Settings → Microphone)"


def test_microphone_hardware_error():
    err = "PortAudioError: -9996 Invalid input device"
    res = format_actionable_error(err, context="mic")
    assert res == "No microphone detected (Settings → Microphone)"


def test_llm_endpoint_unreachable():
    err = "Failed to establish a new connection: [Errno 111] Connection refused"
    res = format_actionable_error(err, context="llm")
    assert res == "LLM endpoint unreachable; pasted raw (Settings → Cleaning)"


def test_llm_timeout():
    err = "HTTPSConnectionPool(host='api.openai.com', port=443): Read timed out."
    res = format_actionable_error(err, context="llm")
    assert res == "LLM endpoint unreachable; pasted raw (Settings → Cleaning)"


def test_session_wayland():
    err = "Running under Wayland"
    res = format_actionable_error(err, context="session")
    assert res == "Session is not X11 (Select X11 at login screen)"


def test_session_missing_display():
    err = "DISPLAY environment variable is not set"
    res = format_actionable_error(err)
    assert res == "Session is not X11 (Select X11 at login screen)"


# =============================================================================
# 2. Overlay state & styling tests
# =============================================================================

def test_overlay_show_error_custom_title():
    from ui.overlay import Overlay

    overlay = Overlay()
    # Directly test the GTK idle implementation _do_show
    overlay._do_show("error", "Test error message", title="Notice")

    assert overlay.state == "error"
    assert overlay.status_title == "Notice"
    assert overlay.status_subtitle == "Test error message"
    assert "error-state" in overlay.win.get_style_context().list_classes()


def test_overlay_show_error_default_title():
    from ui.overlay import Overlay

    overlay = Overlay()
    overlay._do_show("error", "Something went wrong")

    assert overlay.state == "error"
    assert overlay.status_title == "Error"
    assert overlay.status_subtitle == "Something went wrong"
    assert "error-state" in overlay.win.get_style_context().list_classes()


def test_overlay_show_recording_clears_error_class():
    from ui.overlay import Overlay

    overlay = Overlay()
    overlay._do_show("error", "Error")
    assert "error-state" in overlay.win.get_style_context().list_classes()

    overlay._do_show("recording", "")
    assert "error-state" not in overlay.win.get_style_context().list_classes()


# =============================================================================
# 3. app.py error integration tests
# =============================================================================

def test_main_startup_wayland_exit(monkeypatch):
    from app import main

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":0")

    notified = []
    monkeypatch.setattr("app.notify", lambda app_name, msg: notified.append((app_name, msg)))

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert len(notified) == 1
    assert "Session is not X11" in notified[0][1]


def test_main_startup_missing_display_exit(monkeypatch):
    from app import main

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("DISPLAY", raising=False)

    notified = []
    monkeypatch.setattr("app.notify", lambda app_name, msg: notified.append((app_name, msg)))

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert len(notified) == 1
    assert "Session is not X11" in notified[0][1]


def test_main_startup_init_failure_exit(monkeypatch):
    from app import main

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")

    def fake_autotype():
        raise RuntimeError("Missing DEEPGRAM_API_KEY in .env.")

    monkeypatch.setattr("app.AutoType", fake_autotype)

    notified = []
    monkeypatch.setattr("app.notify", lambda app_name, msg: notified.append((app_name, msg)))

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert len(notified) == 1
    assert "Settings → Speech" in notified[0][1]


def test_start_recording_no_mic_detected(isolated_xdg, monkeypatch):
    monkeypatch.setattr("app.create_transcriber", lambda: MagicMock())
    monkeypatch.setattr("audio.devices.list_input_devices", lambda: [])

    from app import AutoType

    app = AutoType()
    app.overlay = MagicMock()
    app.tray = MagicMock()

    app.start_recording()

    assert not app.is_recording
    app.overlay.show_error.assert_called_once_with(
        "No microphone detected (Settings → Microphone)",
        title="Error",
    )


def test_start_stream_no_mic_detected(isolated_xdg, monkeypatch):
    monkeypatch.setattr("app.create_transcriber", lambda: MagicMock())
    monkeypatch.setattr("audio.devices.list_input_devices", lambda: [])

    from app import AutoType

    app = AutoType()
    app.overlay = MagicMock()
    app.tray = MagicMock()

    app.start_stream()

    assert not app.streaming
    app.overlay.show_error.assert_called_once_with(
        "No microphone detected (Settings → Microphone)",
        title="Error",
    )


def test_llm_unreachable_pastes_raw_and_notifies(isolated_xdg, monkeypatch):
    monkeypatch.setattr("app.create_transcriber", lambda: MagicMock())

    from app import AutoType

    app = AutoType()
    app.overlay = MagicMock()
    app.tray = MagicMock()

    # Mock processor to simulate connection error / unreachable endpoint
    def fake_process(*args, **kwargs):
        raise ConnectionError("Failed to connect to LLM provider at http://localhost:11434")

    app.processor.process = fake_process

    pasted = []
    monkeypatch.setattr("app.insert_text", lambda text: pasted.append(text))

    # Run pipeline with clean mode
    app.processing_mode = "clean"
    app.process_and_insert("hello world this is a test transcript")

    # 1. Check that normalized transcript was still pasted
    assert len(pasted) == 1
    assert "hello world" in pasted[0].lower()

    # 2. Check that overlay showed warm-orange notice
    app.overlay.show_error.assert_called_once_with(
        "LLM endpoint unreachable; pasted raw (Settings → Cleaning)",
        title="Notice",
    )
