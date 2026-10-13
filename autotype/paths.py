"""XDG and project path resolution for AutoType."""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("autotype.paths")


def find_repo_root() -> Path | None:
    """Find repository root by looking for .git folder upwards from this file."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / ".git").is_dir():
            return parent
    return None


def get_config_dir() -> Path:
    """Return the configuration directory ($XDG_CONFIG_HOME/autotype)."""
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    config_dir = base / "autotype"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Return the configuration file path ($XDG_CONFIG_HOME/autotype/config.toml)."""
    return get_config_dir() / "config.toml"


def get_state_dir() -> Path:
    """Return the state directory ($XDG_STATE_HOME/autotype, default ~/.local/state/autotype)."""
    xdg = os.getenv("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    state_dir = base / "autotype"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_log_path() -> Path:
    """Return the log file path ($XDG_STATE_HOME/autotype/autotype.log)."""
    return get_state_dir() / "autotype.log"


_logged_data_mode = False


def get_data_dir() -> Path:
    """Return the user data directory.

    If running from a git checkout and the project-relative data/ folder exists,
    use it (development mode) and log the choice.
    Otherwise, use $XDG_DATA_HOME/autotype (default ~/.local/share/autotype).
    """
    global _logged_data_mode

    repo_root = find_repo_root()
    if repo_root and (repo_root / ".git").exists():
        legacy_data = repo_root / "data"
        if legacy_data.is_dir():
            if not _logged_data_mode:
                log.info("Using project-relative data directory: %s (git checkout mode)", legacy_data)
                _logged_data_mode = True
            return legacy_data

    xdg_data = os.getenv("XDG_DATA_HOME")
    base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
    data_dir = base / "autotype"
    data_dir.mkdir(parents=True, exist_ok=True)
    if not _logged_data_mode:
        log.info("Using XDG data directory: %s (XDG mode)", data_dir)
        _logged_data_mode = True
    return data_dir


def get_xdg_data_dir() -> Path:
    """Return standard $XDG_DATA_HOME/autotype directory."""
    xdg_data = os.getenv("XDG_DATA_HOME")
    base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
    d = base / "autotype"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_models_dir() -> Path:
    """Return $XDG_DATA_HOME/autotype/models directory."""
    d = get_xdg_data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_bin_dir() -> Path:
    """Return $XDG_DATA_HOME/autotype/bin directory."""
    d = get_xdg_data_dir() / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_staging_dir() -> Path:
    """Return temporary staging directory inside XDG data directory."""
    d = get_xdg_data_dir() / ".tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_manifest_path() -> Path:
    """Locate models/manifest.json from repository or package resources."""
    repo = find_repo_root()
    if repo:
        p = repo / "models" / "manifest.json"
        if p.is_file():
            return p
    for candidate in [
        Path(__file__).resolve().parent.parent / "models" / "manifest.json",
        Path.cwd() / "models" / "manifest.json",
    ]:
        if candidate.is_file():
            return candidate

    try:
        import importlib.resources as pkg_resources
        traversable = pkg_resources.files("autotype").joinpath("manifest.json")
        cand_path = Path(str(traversable))
        if cand_path.is_file():
            return cand_path
    except Exception:
        pass

    return Path(__file__).resolve().parent.parent / "models" / "manifest.json"

