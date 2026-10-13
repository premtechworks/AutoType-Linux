"""Unit tests for ui.first_run dialog and logic."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from autotype import config
from autotype.manifest import ManifestItem
from ui.first_run import FirstRunDialog, is_first_run_needed


@pytest.fixture
def clean_config(isolated_xdg):
    config.save_config({
        "general": {"first_run_completed": False},
        "stt": {"deepgram_api_key": "", "cloud_api_key": ""},
    })
    return isolated_xdg


def test_first_run_needed_when_no_key_and_no_model(clean_config, monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("CLOUD_STT_API_KEY", raising=False)
    monkeypatch.delenv("FIRST_RUN_COMPLETED", raising=False)
    monkeypatch.setattr("autotype.manifest.is_item_installed", lambda item: False)

    assert is_first_run_needed() is True


def test_first_run_not_needed_if_already_completed(clean_config, monkeypatch):
    monkeypatch.setattr("autotype.manifest.is_item_installed", lambda item: False)
    config.set_first_run_completed(True)

    assert is_first_run_needed() is False


def test_first_run_not_needed_if_cloud_key_present(clean_config, monkeypatch):
    monkeypatch.setattr("autotype.manifest.is_item_installed", lambda item: False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg_test_key_12345")

    assert is_first_run_needed() is False


def test_first_run_not_needed_if_local_model_installed(clean_config, monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("CLOUD_STT_API_KEY", raising=False)
    monkeypatch.setattr("autotype.manifest.is_item_installed", lambda item: True)

    assert is_first_run_needed() is False


def test_dialog_dismiss_sets_first_run_completed(clean_config):
    dialog = FirstRunDialog()
    assert config.first_run_completed() is False
    dialog._on_dismiss()
    assert config.first_run_completed() is True


def test_dialog_setup_cloud_sets_first_run_completed_and_launches_settings(clean_config):
    dialog = FirstRunDialog()
    with patch("subprocess.Popen") as mock_popen:
        dialog._on_setup_cloud(None)
        assert config.first_run_completed() is True
        assert mock_popen.called
        args = mock_popen.call_args[0][0]
        assert "--page=speech" in args


def test_dialog_install_local_downloads_and_sets_backend(clean_config, monkeypatch):
    dialog = FirstRunDialog()
    downloaded_items = []

    def fake_download(item, progress_callback=None, cancel_event=None):
        downloaded_items.append(item.id)

    monkeypatch.setattr("autotype.downloader.download_item", fake_download)

    # Trigger install local
    dialog._on_install_local(None)

    # Allow worker thread to run
    import time
    for _ in range(50):
        if config.first_run_completed():
            break
        time.sleep(0.05)

    assert config.first_run_completed() is True
    cfg = config.load_config()
    assert cfg.get("stt", {}).get("backend") == "parakeet_stream"
