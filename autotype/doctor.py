"""Diagnostics engine for AutoType (autotype doctor).

Performs environment, dependency, and configuration health checks
without making any network requests or starting audio capture.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from typing import Any, Literal

from autotype.__version__ import __version__
from autotype import paths

CheckStatus = Literal["PASS", "WARN", "FAIL"]


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    fix_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "message": self.message,
        }
        if self.fix_hint is not None:
            d["fix_hint"] = self.fix_hint
        return d


@dataclass
class DoctorReport:
    version: str
    ok: bool
    summary: dict[str, int]
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "ok": self.ok,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }


def check_session_type() -> CheckResult:
    """Check session type (X11 required; Wayland unsupported)."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    display = os.environ.get("DISPLAY", "").strip()

    if session_type == "wayland":
        return CheckResult(
            name="Session Type",
            status="FAIL",
            message="Running under Wayland (AutoType requires X11 for synthetic keystrokes and window tracking).",
            fix_hint="Log out and select an X11 / Xorg desktop session at your display manager login screen.",
        )

    if not display:
        return CheckResult(
            name="Session Type",
            status="FAIL",
            message="DISPLAY environment variable is not set.",
            fix_hint="Ensure an X11 display is active or export DISPLAY=:0.",
        )

    return CheckResult(
        name="Session Type",
        status="PASS",
        message=f"X11 session detected (DISPLAY={display}, session={session_type or 'x11'}).",
    )


def check_python_version() -> CheckResult:
    """Check Python runtime version (>= 3.10 required)."""
    ver = sys.version_info
    ver_str = f"{ver[0]}.{ver[1]}.{ver[2]}"
    if (ver[0], ver[1]) >= (3, 10):
        return CheckResult(
            name="Python Version",
            status="PASS",
            message=f"Python {ver_str} (>= 3.10 required).",
        )
    return CheckResult(
        name="Python Version",
        status="FAIL",
        message=f"Python {ver_str} is unsupported (>= 3.10 required).",
        fix_hint="Upgrade to Python 3.10 or newer.",
    )


def check_system_tools() -> list[CheckResult]:
    """Check optional fallback and helper (xclip, xdotool, pactl, notify-send) system binaries."""
    results: list[CheckResult] = []

    # xclip (Optional fallback - GTK3 Gtk.Clipboard is primary)
    xclip_path = shutil.which("xclip")
    if xclip_path:
        results.append(CheckResult("Tool xclip", "PASS", f"found ({xclip_path})"))
    else:
        results.append(CheckResult(
            "Tool xclip",
            "WARN",
            "xclip is missing (optional fallback; GTK3 clipboard is primary).",
            "Install xclip: sudo apt install xclip",
        ))

    # xdotool (Optional fallback - python-xlib is primary)
    xdotool_path = shutil.which("xdotool")
    if xdotool_path:
        results.append(CheckResult("Tool xdotool", "PASS", f"found ({xdotool_path})"))
    else:
        results.append(CheckResult(
            "Tool xdotool",
            "WARN",
            "xdotool is missing (optional fallback; python-xlib is primary).",
            "Install xdotool: sudo apt install xdotool",
        ))

    # pactl (Optional)
    pactl_path = shutil.which("pactl")
    if pactl_path:
        results.append(CheckResult("Tool pactl", "PASS", f"found ({pactl_path})"))
    else:
        results.append(CheckResult(
            "Tool pactl",
            "WARN",
            "pactl is missing (optional for Bluetooth headset profile auto-switching).",
            "Install pulseaudio-utils: sudo apt install pulseaudio-utils",
        ))

    # notify-send (Optional)
    notify_path = shutil.which("notify-send")
    if notify_path:
        results.append(CheckResult("Tool notify-send", "PASS", f"found ({notify_path})"))
    else:
        results.append(CheckResult(
            "Tool notify-send",
            "WARN",
            "notify-send is missing (optional for desktop notifications).",
            "Install libnotify-bin: sudo apt install libnotify-bin",
        ))

    return results


def check_audio_devices() -> CheckResult:
    """Check audio capture devices using the existing audio module without recording."""
    try:
        from audio.devices import list_input_devices

        devices = list_input_devices()
        if devices:
            names = [d.get("name", "unknown") for d in devices[:2]]
            sample = ", ".join(names)
            return CheckResult(
                name="Audio Capture",
                status="PASS",
                message=f"{len(devices)} input device(s) found ({sample}).",
            )
        return CheckResult(
            name="Audio Capture",
            status="FAIL",
            message="No audio capture devices detected.",
            fix_hint="Connect a microphone or verify audio permissions in Settings → Microphone.",
        )
    except Exception as exc:
        return CheckResult(
            name="Audio Capture",
            status="FAIL",
            message=f"Failed to query audio capture devices: {exc}",
            fix_hint="Ensure PortAudio / sounddevice is installed and functional.",
        )


def check_gtk3_gobject() -> CheckResult:
    """Check GTK3 and GObject introspection availability without crashing."""
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk  # noqa: F401

        return CheckResult(
            name="GTK3 / GObject",
            status="PASS",
            message="GTK3 and GObject introspection bindings are available.",
        )
    except Exception as exc:
        return CheckResult(
            name="GTK3 / GObject",
            status="FAIL",
            message=f"GTK3 or GObject introspection bindings are missing ({exc}).",
            fix_hint="Install GTK3 bindings: sudo apt install python3-gi gir1.2-gtk-3.0",
        )


def check_config_file() -> CheckResult:
    """Check config file existence, readability, and 0600 permissions."""
    cfg_path = paths.get_config_path()
    if not cfg_path.exists():
        return CheckResult(
            name="Config File",
            status="WARN",
            message=f"Config file not found at {cfg_path}.",
            fix_hint="Launch autotype settings or create ~/.config/autotype/config.toml.",
        )

    # Check readability
    try:
        _ = cfg_path.read_text(encoding="utf-8")
    except Exception as exc:
        return CheckResult(
            name="Config File",
            status="FAIL",
            message=f"Config file at {cfg_path} is unreadable: {exc}",
            fix_hint=f"Check read permissions on {cfg_path}.",
        )

    # Check permissions 0600
    try:
        mode = stat.S_IMODE(os.stat(cfg_path).st_mode)
        if mode == 0o600:
            return CheckResult(
                name="Config File",
                status="PASS",
                message=f"Config file present and readable with 0600 permissions ({cfg_path}).",
            )
        return CheckResult(
            name="Config File",
            status="WARN",
            message=f"Config file permissions are {oct(mode)} instead of 0600 ({cfg_path}).",
            fix_hint=f"Restrict file permissions to protect API keys: chmod 600 {cfg_path}",
        )
    except Exception as exc:
        return CheckResult(
            name="Config File",
            status="WARN",
            message=f"Could not stat config file permissions: {exc}",
            fix_hint=f"Ensure file permissions are 600: chmod 600 {cfg_path}",
        )


def check_stt_provider() -> CheckResult:
    """Check configured STT backend (cloud API key set, or local binary/model paths exist)."""
    try:
        from autotype import config as cfg

        backend = cfg.stt_backend()

        if cfg.is_cloud_stt():
            if backend == "deepgram":
                has_key = bool(cfg.deepgram_api_key())
                if has_key:
                    return CheckResult(
                        name="STT Backend",
                        status="PASS",
                        message=f"Cloud STT 'deepgram' is configured and API key is set (model={cfg.deepgram_model()}).",
                    )
                return CheckResult(
                    name="STT Backend",
                    status="FAIL",
                    message="Cloud STT 'deepgram' is configured but DEEPGRAM_API_KEY is not set.",
                    fix_hint="Configure your Deepgram API key in Settings → Speech.",
                )
            else:
                has_key = bool(cfg.cloud_stt_api_key())
                provider_name = cfg.cloud_stt_provider()
                if has_key:
                    return CheckResult(
                        name="STT Backend",
                        status="PASS",
                        message=f"Cloud STT '{provider_name}' is configured and API key is set.",
                    )
                return CheckResult(
                    name="STT Backend",
                    status="FAIL",
                    message=f"Cloud STT '{provider_name}' is configured but CLOUD_STT_API_KEY is not set.",
                    fix_hint="Configure your Cloud STT API key in Settings → Speech.",
                )

        if cfg.is_local_stt():
            if backend == "parakeet":
                bin_path = Path(cfg.parakeet_binary())
                model_path = Path(cfg.parakeet_model())
            else:  # parakeet_stream
                bin_path = Path(cfg.parakeet_stream_binary())
                model_path = Path(cfg.parakeet_stream_model())

            bin_ok = bin_path.is_file() and os.access(bin_path, os.X_OK)
            model_ok = model_path.is_file()

            if bin_ok and model_ok:
                return CheckResult(
                    name="STT Backend",
                    status="PASS",
                    message=f"Local STT '{backend}' binary and model paths exist.",
                )

            missing: list[str] = []
            if not bin_ok:
                missing.append(f"binary ({bin_path})")
            if not model_ok:
                missing.append(f"model ({model_path})")

            return CheckResult(
                name="STT Backend",
                status="FAIL",
                message=f"Local STT '{backend}' missing {', '.join(missing)}.",
                fix_hint="Install local models via 'autotype download-model --all-recommended' or Settings → Speech.",
            )

        return CheckResult(
            name="STT Backend",
            status="WARN",
            message=f"Unknown STT backend configured: '{backend}'.",
            fix_hint="Select a supported STT backend in Settings → Speech.",
        )
    except Exception as exc:
        return CheckResult(
            name="STT Backend",
            status="FAIL",
            message=f"Failed to check STT backend: {exc}",
            fix_hint="Check STT settings in Settings → Speech.",
        )


def check_llm_provider() -> CheckResult:
    """Check configured LLM provider and verify whether API key is set."""
    try:
        from autotype import config as cfg

        provider = cfg.llm_provider()

        if provider == "ollama":
            return CheckResult(
                name="LLM Provider",
                status="PASS",
                message="Local LLM provider 'ollama' configured (no API key required).",
            )

        has_key = bool(cfg.llm_api_key())

        if has_key:
            return CheckResult(
                name="LLM Provider",
                status="PASS",
                message=f"LLM provider '{provider}' is configured and API key is set.",
            )

        if provider == "custom":
            return CheckResult(
                name="LLM Provider",
                status="WARN",
                message="Custom LLM provider configured without an API key.",
                fix_hint="Add LLM_API_KEY in Settings → Cleaning if your custom endpoint requires authentication.",
            )

        return CheckResult(
            name="LLM Provider",
            status="FAIL",
            message=f"LLM provider '{provider}' is configured but LLM_API_KEY is not set.",
            fix_hint="Configure your LLM API key in Settings → Cleaning.",
        )
    except Exception as exc:
        return CheckResult(
            name="LLM Provider",
            status="FAIL",
            message=f"Failed to check LLM provider: {exc}",
            fix_hint="Check LLM settings in Settings → Cleaning.",
        )


def check_data_directory() -> CheckResult:
    """Check that user data directory exists and is writable."""
    try:
        data_dir = paths.get_data_dir()
        if not data_dir.is_dir():
            return CheckResult(
                name="Data Directory",
                status="FAIL",
                message=f"Data directory {data_dir} does not exist.",
                fix_hint="Create the directory or verify XDG_DATA_HOME permissions.",
            )
        if os.access(data_dir, os.W_OK):
            return CheckResult(
                name="Data Directory",
                status="PASS",
                message=f"Data directory is writable ({data_dir}).",
            )
        return CheckResult(
            name="Data Directory",
            status="FAIL",
            message=f"Data directory {data_dir} is not writable.",
            fix_hint=f"Grant write permissions to the data directory: chmod u+w {data_dir}",
        )
    except Exception as exc:
        return CheckResult(
            name="Data Directory",
            status="FAIL",
            message=f"Failed to check data directory: {exc}",
            fix_hint="Verify user data directory permissions.",
        )


def check_daemon_status() -> CheckResult:
    """Check daemon status via PID file if present."""
    try:
        pid_file = paths.get_data_dir() / "daemon.pid"
        if not pid_file.is_file():
            return CheckResult(
                name="Daemon Status",
                status="PASS",
                message="Daemon is not running (no PID file present).",
            )

        pid_text = pid_file.read_text(encoding="utf-8").strip()
        try:
            pid = int(pid_text)
        except ValueError:
            return CheckResult(
                name="Daemon Status",
                status="WARN",
                message=f"Corrupt daemon PID file found ({pid_file}).",
                fix_hint=f"Remove corrupt PID file: rm {pid_file}",
            )

        # Check if process is alive
        running = False
        try:
            os.kill(pid, 0)
            running = True
        except (ProcessLookupError, PermissionError):
            pass

        if running:
            return CheckResult(
                name="Daemon Status",
                status="PASS",
                message=f"Daemon is running (PID {pid}).",
            )

        return CheckResult(
            name="Daemon Status",
            status="WARN",
            message=f"Stale daemon PID file found (PID {pid} is not running).",
            fix_hint=f"Remove stale PID file if daemon is not running: rm {pid_file}",
        )
    except Exception as exc:
        return CheckResult(
            name="Daemon Status",
            status="WARN",
            message=f"Could not verify daemon PID file: {exc}",
            fix_hint="Check daemon.pid in the user data directory.",
        )


def run_checks() -> DoctorReport:
    """Execute all diagnostic checks and return a structured DoctorReport.

    Pure function: offline only, zero network requests, zero telemetry,
    and never prints or discloses API keys.
    """
    checks: list[CheckResult] = []

    # 1. Session Type & Display
    checks.append(check_session_type())

    # 2. Python Version
    checks.append(check_python_version())

    # 3. System Tools
    checks.extend(check_system_tools())

    # 4. Audio Capture Devices
    checks.append(check_audio_devices())

    # 5. GTK3 & GObject Introspection
    checks.append(check_gtk3_gobject())

    # 6. Config File & Permissions
    checks.append(check_config_file())

    # 7. Cloud STT & Local STT
    checks.append(check_stt_provider())

    # 8. LLM Provider
    checks.append(check_llm_provider())

    # 9. Data Directory
    checks.append(check_data_directory())

    # 10. Daemon Status
    checks.append(check_daemon_status())

    passed = sum(1 for c in checks if c.status == "PASS")
    warned = sum(1 for c in checks if c.status == "WARN")
    failed = sum(1 for c in checks if c.status == "FAIL")

    return DoctorReport(
        version=__version__,
        ok=(failed == 0),
        summary={
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "total": len(checks),
        },
        checks=checks,
    )


def format_report_text(report: DoctorReport, use_color: bool | None = None) -> str:
    """Format doctor report as clean human-readable terminal output."""
    if use_color is None:
        use_color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    COLOR_GREEN = "\033[32m" if use_color else ""
    COLOR_YELLOW = "\033[33m" if use_color else ""
    COLOR_RED = "\033[31m" if use_color else ""
    COLOR_RESET = "\033[0m" if use_color else ""

    lines = [
        f"AutoType v{report.version} Doctor",
        "-" * 45,
    ]

    for check in report.checks:
        if check.status == "PASS":
            tag = f"{COLOR_GREEN}[PASS]{COLOR_RESET}"
        elif check.status == "WARN":
            tag = f"{COLOR_YELLOW}[WARN]{COLOR_RESET}"
        else:
            tag = f"{COLOR_RED}[FAIL]{COLOR_RESET}"

        lines.append(f"{tag} {check.name:<18}: {check.message}")
        if check.fix_hint:
            lines.append(f"       Hint: {check.fix_hint}")

    lines.append("-" * 45)
    s = report.summary
    status_overall = "All checks passed." if report.ok else f"{s['failed']} check(s) failed."
    lines.append(f"Summary: {s['passed']} passed, {s['warned']} warned, {s['failed']} failed ({status_overall})")

    return "\n".join(lines)


def format_report_json(report: DoctorReport) -> str:
    """Serialize doctor report to formatted JSON string."""
    return json.dumps(report.to_dict(), indent=2)
