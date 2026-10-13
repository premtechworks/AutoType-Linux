"""First-run setup prompt for AutoType."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from autotype import config
from autotype import manifest
from autotype.manifest import get_item, is_item_installed

log = logging.getLogger("autotype.first_run")


def is_first_run_needed() -> bool:
    """Return True if first-run prompt is uncompleted and no STT is configured."""
    if config.first_run_completed():
        return False

    has_cloud_key = bool(config.deepgram_api_key() or config.cloud_stt_api_key())
    if has_cloud_key:
        return False

    stream_model = manifest.get_item("parakeet-eou-120m")
    stream_bin = manifest.get_item("parakeet-cli")
    has_local = bool(
        stream_model
        and manifest.is_item_installed(stream_model)
        and stream_bin
        and manifest.is_item_installed(stream_bin)
    )
    if has_local:
        return False

    return True


class FirstRunDialog(Gtk.Dialog):
    """First-run dialog offering local offline model install or cloud setup."""

    def __init__(self, parent: Gtk.Window | None = None):
        super().__init__(
            title="AutoType Setup",
            transient_for=parent,
            modal=True,
        )
        self.set_default_size(520, 360)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(18)

        content = self.get_content_area()
        content.set_spacing(16)

        # Header Title
        title_lbl = Gtk.Label(xalign=0)
        title_lbl.set_markup("<span size='x-large' weight='bold'>Welcome to AutoType</span>")
        content.pack_start(title_lbl, False, False, 0)

        # Description
        desc_lbl = Gtk.Label(xalign=0)
        desc_lbl.set_line_wrap(True)
        desc_lbl.set_markup(
            "AutoType needs a speech recognition engine to transcribe your voice.\n"
            "Choose whether to download the <b>recommended offline local model</b> "
            "for 100% private on-device dictation, or set up a high-speed <b>cloud provider</b>."
        )
        content.pack_start(desc_lbl, False, False, 0)

        # Progress bar (hidden by default)
        self.pbar = Gtk.ProgressBar()
        self.pbar.set_size_request(-1, 20)
        self.pbar.set_no_show_all(True)
        content.pack_start(self.pbar, False, False, 4)

        self.status_lbl = Gtk.Label(xalign=0)
        self.status_lbl.get_style_context().add_class("dim-label")
        self.status_lbl.set_no_show_all(True)
        content.pack_start(self.status_lbl, False, False, 0)

        # Options Box
        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.pack_start(options_box, True, True, 8)

        # 1. Local Offline Model Button
        self.btn_local = Gtk.Button()
        local_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        local_box.set_margin_start(12)
        local_box.set_margin_end(12)
        local_box.set_margin_top(8)
        local_box.set_margin_bottom(8)
        l_title = Gtk.Label(xalign=0)
        l_title.set_markup("<b>Download Recommended Local Model</b>")
        l_desc = Gtk.Label(xalign=0)
        l_desc.get_style_context().add_class("dim-label")
        l_desc.set_text("Offline Parakeet 120M streaming model & engine (170 MB). No internet required.")
        local_box.pack_start(l_title, False, False, 0)
        local_box.pack_start(l_desc, False, False, 0)
        self.btn_local.add(local_box)
        self.btn_local.get_style_context().add_class("suggested-action")
        self.btn_local.connect("clicked", self._on_install_local)
        options_box.pack_start(self.btn_local, False, False, 0)

        # 2. Cloud Provider Setup Button
        self.btn_cloud = Gtk.Button()
        cloud_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cloud_box.set_margin_start(12)
        cloud_box.set_margin_end(12)
        cloud_box.set_margin_top(8)
        cloud_box.set_margin_bottom(8)
        c_title = Gtk.Label(xalign=0)
        c_title.set_markup("<b>Set Up Cloud Speech Provider</b>")
        c_desc = Gtk.Label(xalign=0)
        c_desc.get_style_context().add_class("dim-label")
        c_desc.set_text("Configure API keys for Deepgram, OpenAI Whisper, Groq, or NVIDIA NIM.")
        cloud_box.pack_start(c_title, False, False, 0)
        cloud_box.pack_start(c_desc, False, False, 0)
        self.btn_cloud.add(cloud_box)
        self.btn_cloud.connect("clicked", self._on_setup_cloud)
        options_box.pack_start(self.btn_cloud, False, False, 0)

        # Dismiss / Decide Later button
        btn_skip = self.add_button("Decide Later", Gtk.ResponseType.CLOSE)
        btn_skip.connect("clicked", lambda _b: self._on_dismiss())

        self.connect("delete-event", lambda _w, _e: self._on_dismiss())

    def _on_dismiss(self):
        config.set_first_run_completed(True)
        self.destroy()

    def _on_setup_cloud(self, _btn):
        config.set_first_run_completed(True)
        self.destroy()
        settings_script = Path(__file__).resolve().parent.parent / "settings_gui.py"
        try:
            subprocess.Popen([sys.executable, str(settings_script), "--page=speech"])
        except Exception as exc:
            log.warning("Could not launch settings GUI: %s", exc)

    def _on_install_local(self, _btn):
        from autotype.downloader import download_item

        self.btn_local.set_sensitive(False)
        self.btn_cloud.set_sensitive(False)
        self.pbar.set_no_show_all(False)
        self.pbar.show()
        self.status_lbl.set_no_show_all(False)
        self.status_lbl.show()
        self.status_lbl.set_text("Downloading offline speech engine and model…")

        def _worker():
            try:
                items = [get_item("parakeet-cli"), get_item("parakeet-eou-120m")]
                for idx, item in enumerate(items, 1):
                    if not item:
                        continue
                    if is_item_installed(item):
                        continue

                    def on_progress(dl, total):
                        frac = (dl / total) if total > 0 else 0.0
                        GLib.idle_add(self._update_progress, idx, len(items), frac, item.display_name)

                    download_item(item, progress_callback=on_progress)

                # Configure local STT backend in config.toml
                cfg = config.load_config()
                if "stt" not in cfg or not isinstance(cfg["stt"], dict):
                    cfg["stt"] = {}
                cfg["stt"]["backend"] = "parakeet_stream"
                config.save_config(cfg)
                config.set_first_run_completed(True)

                GLib.idle_add(self._on_download_complete, True, None)
            except Exception as exc:
                log.error("First-run model download failed: %s", exc)
                GLib.idle_add(self._on_download_complete, False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_progress(self, idx, total_items, frac, item_name):
        overall_frac = ((idx - 1) + frac) / total_items
        self.pbar.set_fraction(overall_frac)
        self.status_lbl.set_text(f"[{idx}/{total_items}] Downloading {item_name} ({frac*100:.0f}%)…")
        return False

    def _on_download_complete(self, success: bool, error_msg: str | None):
        if success:
            self.status_lbl.set_text("Installation complete! AutoType is ready.")
            self.destroy()
        else:
            self.status_lbl.set_text(f"Installation failed: {error_msg}")
            self.btn_local.set_sensitive(True)
            self.btn_cloud.set_sensitive(True)
        return False


def check_and_show_first_run(parent: Gtk.Window | None = None) -> bool:
    """Check if first-run setup prompt is needed, and display it if so."""
    if not is_first_run_needed():
        return False

    if not os.environ.get("DISPLAY"):
        log.info("No DISPLAY available; skipping first-run dialog.")
        return False

    dialog = FirstRunDialog(parent=parent)
    dialog.show_all()
    dialog.run()
    return True
