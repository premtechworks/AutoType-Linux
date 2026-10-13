"""Unit tests for path resolution and XDG directory handling."""
import logging
from pathlib import Path
import pytest

from autotype import paths


def test_custom_xdg_config_dir(tmp_path, monkeypatch):
    custom_config = tmp_path / "custom_config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_config))

    cfg_dir = paths.get_config_dir()
    assert cfg_dir == custom_config / "autotype"
    assert cfg_dir.is_dir()

    cfg_file = paths.get_config_path()
    assert cfg_file == custom_config / "autotype" / "config.toml"


def test_default_xdg_config_dir(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    fake_home = Path("/tmp/fake_home_test_autotype")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    cfg_dir = paths.get_config_dir()
    assert cfg_dir == fake_home / ".config" / "autotype"


def test_git_checkout_mode_prefers_project_data(tmp_path, monkeypatch, caplog):
    # Simulate a git repo root with a data/ folder
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    (fake_repo / ".git").mkdir()
    fake_data = fake_repo / "data"
    fake_data.mkdir()

    monkeypatch.setattr(paths, "find_repo_root", lambda: fake_repo)
    paths._logged_data_mode = False

    with caplog.at_level(logging.INFO):
        data_dir = paths.get_data_dir()

    assert data_dir == fake_data
    assert "git checkout mode" in caplog.text


def test_xdg_data_mode_when_no_git_data(tmp_path, monkeypatch, caplog):
    # Simulate non-git or git without data/ folder
    custom_data_home = tmp_path / "custom_share"
    monkeypatch.setenv("XDG_DATA_HOME", str(custom_data_home))
    monkeypatch.setattr(paths, "find_repo_root", lambda: None)
    paths._logged_data_mode = False

    with caplog.at_level(logging.INFO):
        data_dir = paths.get_data_dir()

    assert data_dir == custom_data_home / "autotype"
    assert data_dir.is_dir()
    assert "XDG mode" in caplog.text


def test_default_xdg_data_dir(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    fake_home = Path("/tmp/fake_home_test_autotype")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(paths, "find_repo_root", lambda: None)
    paths._logged_data_mode = False

    data_dir = paths.get_data_dir()
    assert data_dir == fake_home / ".local" / "share" / "autotype"


def test_custom_xdg_state_dir(tmp_path, monkeypatch):
    custom_state = tmp_path / "custom_state"
    monkeypatch.setenv("XDG_STATE_HOME", str(custom_state))

    state_dir = paths.get_state_dir()
    assert state_dir == custom_state / "autotype"
    assert state_dir.is_dir()

    log_path = paths.get_log_path()
    assert log_path == custom_state / "autotype" / "autotype.log"


def test_default_xdg_state_dir(monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    fake_home = Path("/tmp/fake_home_test_autotype")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    state_dir = paths.get_state_dir()
    assert state_dir == fake_home / ".local" / "state" / "autotype"
    assert paths.get_log_path() == fake_home / ".local" / "state" / "autotype" / "autotype.log"


def test_models_and_bin_paths(tmp_path, monkeypatch):
    custom_data = tmp_path / "share"
    monkeypatch.setenv("XDG_DATA_HOME", str(custom_data))

    assert paths.get_models_dir() == custom_data / "autotype" / "models"
    assert paths.get_models_dir().is_dir()

    assert paths.get_bin_dir() == custom_data / "autotype" / "bin"
    assert paths.get_bin_dir().is_dir()

    assert paths.get_staging_dir() == custom_data / "autotype" / ".tmp"
    assert paths.get_staging_dir().is_dir()


def test_manifest_path_discovery():
    manifest_path = paths.get_manifest_path()
    assert manifest_path.is_file()
    assert manifest_path.name == "manifest.json"

