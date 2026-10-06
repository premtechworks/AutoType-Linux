#!/usr/bin/env python3
"""AutoType Settings — Linux Mint XFCE control panel (GTK3).

Tabs: Speech-to-Text | Cleaning (LLM) | Prompt | Mode & Voice |
      Microphone | General.

Writes straight to .env (what the daemon reads) plus
data/gui_settings.json (named profiles), data/custom_prompt.txt and
data/vocabulary.json. Restart the daemon after changing STT/mic settings.

Launch:  .venv/bin/python settings_gui.py   (or ./open-settings.sh)
"""
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from llm.prompts import SYSTEM_PROMPT  # noqa: E402
from ui import settings_store as store  # noqa: E402


def _row(label_text, widget, tooltip=None):
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    label = Gtk.Label(label=label_text, xalign=0)
    label.set_size_request(190, -1)
    box.pack_start(label, False, False, 0)
    box.pack_start(widget, True, True, 0)
    if tooltip:
        box.set_tooltip_text(tooltip)
    return box


def _entry(text="", secret=False, placeholder=""):
    e = Gtk.Entry()
    e.set_text(text or "")
    e.set_visibility(not secret)
    if placeholder:
        e.set_placeholder_text(placeholder)
    return e


class SettingsWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="AutoType Settings")
        self.set_default_size(760, 620)
        self.set_border_width(10)
        self.env = store.load_env()
        self.profiles = store.load_profiles()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(vbox)

        self.nb = Gtk.Notebook()
        vbox.pack_start(self.nb, True, True, 0)

        self._build_stt_tab()
        self._build_clean_tab()
        self._build_prompt_tab()
        self._build_mode_tab()
        self._build_mic_tab()
        self._build_general_tab()

        self.status = Gtk.Label(label="Ready. Changes apply on Save — "
                                      "restart the daemon for STT/mic changes.")
        self.status.set_xalign(0)
        vbox.pack_start(self.status, False, False, 0)

        quit_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        quit_row.set_halign(Gtk.Align.END)
        restart_btn = Gtk.Button(label="Restart daemon")
        restart_btn.connect("clicked", self._on_restart_daemon)
        quit_row.pack_start(restart_btn, False, False, 0)
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda *_: Gtk.main_quit())
        quit_row.pack_start(close_btn, False, False, 0)
        vbox.pack_start(quit_row, False, False, 0)

    # -- helpers ---------------------------------------------------------
    def say(self, text):
        GLib.idle_add(self.status.set_text, text)

    def run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _profile_row(self, names, active, on_change, on_save, on_delete):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        combo = Gtk.ComboBoxText()
        for n in names:
            combo.append_text(n)
        try:
            combo.set_active(names.index(active))
        except ValueError:
            combo.set_active(0)
        combo.connect("changed", on_change)
        box.pack_start(Gtk.Label(label="Profile:", xalign=0), False, False, 0)
        box.pack_start(combo, True, True, 0)
        save_btn = Gtk.Button(label="Save")
        save_btn.connect("clicked", on_save)
        box.pack_start(save_btn, False, False, 0)
        new_btn = Gtk.Button(label="Save as…")
        new_btn.connect("clicked", self._on_save_as(on_save))
        box.pack_start(new_btn, False, False, 0)
        del_btn = Gtk.Button(label="Delete")
        del_btn.connect("clicked", on_delete)
        box.pack_start(del_btn, False, False, 0)
        return box, combo

    def _on_save_as(self, on_save):
        def _inner(_btn):
            dlg = Gtk.Dialog(title="Save profile as…", parent=self,
                             flags=0)
            dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
            entry = Gtk.Entry()
            entry.set_placeholder_text("Profile name")
            dlg.get_content_area().pack_start(entry, True, True, 0)
            dlg.show_all()
            if dlg.run() == Gtk.ResponseType.OK and entry.get_text().strip():
                on_save(_btn, name=entry.get_text().strip())
            dlg.destroy()
        return _inner

    def _combo_value(self, combo):
        return combo.get_active_text() or ""

    # -- Tab 1: STT -------------------------------------------------------
    def _build_stt_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)
        self.nb.append_page(page, Gtk.Label(label="Speech-to-Text"))

        names = list(self.profiles["stt_profiles"])
        row, self.stt_combo = self._profile_row(
            names, self.profiles.get("active_stt", names[0]),
            self._on_stt_select, self._on_stt_save, self._on_stt_delete)
        page.pack_start(row, False, False, 0)

        cur = self.profiles["stt_profiles"][self._combo_value(self.stt_combo)]
        self.stt_backend = Gtk.ComboBoxText()
        for b in ("deepgram", "parakeet", "parakeet_stream"):
            self.stt_backend.append_text(b)
        labels = {"deepgram": "Deepgram (cloud, streaming)",
                  "parakeet": "Parakeet (local, batch)",
                  "parakeet_stream": "Parakeet stream (local, EOU)"}
        # show friendly names via tooltip; store raw value
        self.stt_backend.set_tooltip_text(
            "deepgram = cloud Flux streaming; parakeet = offline batch; "
            "parakeet_stream = offline 120M EOU streaming.")
        try:
            self.stt_backend.set_active(
                ("deepgram", "parakeet", "parakeet_stream").index(
                    cur.get("STT_BACKEND", "deepgram")))
        except ValueError:
            self.stt_backend.set_active(0)
        page.pack_start(_row("Backend", self.stt_backend,
                             "Cloud = needs internet + API key. "
                             "Local = offline, needs model file."), False, False, 0)
        page.pack_start(Gtk.Label(
            label="Deepgram (cloud) — console.deepgram.com, Token auth",
            xalign=0), False, False, 0)
        self.f_dg_key = _entry(cur.get("DEEPGRAM_API_KEY"), secret=True)
        self.f_dg_model = _entry(cur.get("DEEPGRAM_MODEL"), placeholder="nova-3")
        self.f_dg_lang = _entry(cur.get("DEEPGRAM_LANGUAGE"), placeholder="en-US")
        self.f_dg_flux = _entry(cur.get("DEEPGRAM_FLUX_MODEL"),
                               placeholder="flux-general-en")
        page.pack_start(_row("API key", self.f_dg_key), False, False, 0)
        page.pack_start(_row("Batch model", self.f_dg_model), False, False, 0)
        page.pack_start(_row("Language", self.f_dg_lang), False, False, 0)
        page.pack_start(_row("Flux model", self.f_dg_flux,
                             "Streaming model used for toggle-to-talk."),
                        False, False, 0)
        page.pack_start(Gtk.Label(label="Parakeet (local, offline)", xalign=0),
                        False, False, 0)
        self.f_pk_bin = _entry(cur.get("PARAKEET_BINARY"))
        self.f_pk_model = _entry(cur.get("PARAKEET_MODEL"))
        self.f_pks_bin = _entry(cur.get("PARAKEET_STREAM_BINARY"))
        self.f_pks_model = _entry(cur.get("PARAKEET_STREAM_MODEL"))
        page.pack_start(_row("Batch binary", self.f_pk_bin), False, False, 0)
        page.pack_start(_row("Batch model", self.f_pk_model), False, False, 0)
        page.pack_start(_row("Stream binary", self.f_pks_bin), False, False, 0)
        page.pack_start(_row("Stream model", self.f_pks_model), False, False, 0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        test_key = Gtk.Button(label="Test Deepgram key")
        test_key.connect("clicked", self._on_test_dg_key)
        btn_row.pack_start(test_key, False, False, 0)
        test_bin = Gtk.Button(label="Check local binaries")
        test_bin.connect("clicked", self._on_test_binaries)
        btn_row.pack_start(test_bin, False, False, 0)
        page.pack_start(btn_row, False, False, 0)
        page.pack_start(Gtk.Label(
            label="Tip: keep one profile per use (e.g. “Cloud”, “Offline”). "
                  "Switching profiles rewrites .env immediately.",
            xalign=0, wrap=True), False, False, 0)

    def _stt_fields(self):
        return {
            "STT_BACKEND": self._combo_value(self.stt_backend) or "deepgram",
            "DEEPGRAM_API_KEY": self.f_dg_key.get_text().strip(),
            "DEEPGRAM_MODEL": self.f_dg_model.get_text().strip() or "nova-3",
            "DEEPGRAM_LANGUAGE": self.f_dg_lang.get_text().strip() or "en-US",
            "DEEPGRAM_FLUX_MODEL": self.f_dg_flux.get_text().strip()
            or "flux-general-en",
            "PARAKEET_BINARY": self.f_pk_bin.get_text().strip(),
            "PARAKEET_MODEL": self.f_pk_model.get_text().strip(),
            "PARAKEET_STREAM_BINARY": self.f_pks_bin.get_text().strip(),
            "PARAKEET_STREAM_MODEL": self.f_pks_model.get_text().strip(),
        }

    def _fill_stt(self, prof):
        self.f_dg_key.set_text(prof.get("DEEPGRAM_API_KEY", ""))
        self.f_dg_model.set_text(prof.get("DEEPGRAM_MODEL", "nova-3"))
        self.f_dg_lang.set_text(prof.get("DEEPGRAM_LANGUAGE", "en-US"))
        self.f_dg_flux.set_text(prof.get("DEEPGRAM_FLUX_MODEL",
                                         "flux-general-en"))
        self.f_pk_bin.set_text(prof.get("PARAKEET_BINARY", ""))
        self.f_pk_model.set_text(prof.get("PARAKEET_MODEL", ""))
        self.f_pks_bin.set_text(prof.get("PARAKEET_STREAM_BINARY", ""))
        self.f_pks_model.set_text(prof.get("PARAKEET_STREAM_MODEL", ""))
        try:
            self.stt_backend.set_active(
                ("deepgram", "parakeet", "parakeet_stream").index(
                    prof.get("STT_BACKEND", "deepgram")))
        except ValueError:
            self.stt_backend.set_active(0)

    def _on_stt_select(self, combo):
        name = self._combo_value(combo)
        prof = self.profiles["stt_profiles"].get(name)
        if prof:
            self._fill_stt(prof)

    def _on_stt_save(self, _btn, name=None):
        name = name or self._combo_value(self.stt_combo)
        if not name:
            return
        self.profiles["stt_profiles"][name] = self._stt_fields()
        self.profiles["active_stt"] = name
        store.save_profiles(self.profiles)
        store.save_env(self._stt_fields())
        self._refresh_combo(self.stt_combo,
                            list(self.profiles["stt_profiles"]), name)
        self.say(f"STT profile “{name}” saved to .env. Restart daemon to apply.")

    def _on_stt_delete(self, _btn):
        name = self._combo_value(self.stt_combo)
        if len(self.profiles["stt_profiles"]) <= 1:
            self.say("Cannot delete the last STT profile.")
            return
        self.profiles["stt_profiles"].pop(name, None)
        new_active = list(self.profiles["stt_profiles"])[0]
        self.profiles["active_stt"] = new_active
        store.save_profiles(self.profiles)
        self._refresh_combo(self.stt_combo,
                            list(self.profiles["stt_profiles"]), new_active)
        self._fill_stt(self.profiles["stt_profiles"][new_active])
        self.say(f"Deleted “{name}”. Active: “{new_active}”.")

    def _refresh_combo(self, combo, names, active):
        combo.remove_all()
        for n in names:
            combo.append_text(n)
        try:
            combo.set_active(names.index(active))
        except ValueError:
            combo.set_active(0)

    def _on_test_dg_key(self, _btn):
        self.say("Testing Deepgram key…")
        key = self.f_dg_key.get_text().strip()

        def _work():
            import requests
            try:
                r = requests.get("https://api.deepgram.com/v1/projects",
                                 headers={"Authorization": f"Token {key}"},
                                 timeout=15)
                if r.status_code == 200:
                    self.say("Deepgram key OK.")
                else:
                    self.say(f"Deepgram key failed: HTTP {r.status_code}.")
            except Exception as exc:
                self.say(f"Deepgram test failed: {exc}")
        self.run_bg(_work)

    def _on_test_binaries(self, _btn):
        msgs = []
        for label, path in (("batch binary", self.f_pk_bin.get_text().strip()),
                            ("batch model", self.f_pk_model.get_text().strip()),
                            ("stream binary", self.f_pks_bin.get_text().strip()),
                            ("stream model", self.f_pks_model.get_text().strip())):
            ok = bool(path) and Path(path).exists()
            msgs.append(f"{label}: {'OK' if ok else 'MISSING'}")
        self.say("  •  ".join(msgs))

    # -- Tab 2: Cleaning (LLM) -------------------------------------------
    def _build_clean_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)
        self.nb.append_page(page, Gtk.Label(label="Cleaning (LLM)"))

        names = list(self.profiles["clean_profiles"])
        row, self.clean_combo = self._profile_row(
            names, self.profiles.get("active_clean", names[0]),
            self._on_clean_select, self._on_clean_save, self._on_clean_delete)
        page.pack_start(row, False, False, 0)

        cur = self.profiles["clean_profiles"][self._combo_value(self.clean_combo)]
        self.f_or_url = _entry(cur.get("OMNIROUTE_BASE_URL"),
                               placeholder="http://127.0.0.1:20128")
        self.f_or_key = _entry(cur.get("OMNIROUTE_API_KEY"), secret=True)
        self.f_or_model = _entry(cur.get("OMNIROUTE_MODEL"), placeholder="auto")
        self.f_or_temp = _entry(cur.get("CLEANING_TEMPERATURE", "0.1"),
                                placeholder="0.1")
        page.pack_start(_row("Base URL", self.f_or_url,
                             "Any OpenAI-compatible /v1 endpoint: local "
                             "OmniRoute, remote OmniRoute, Ollama, etc."),
                        False, False, 0)
        page.pack_start(_row("API key", self.f_or_key), False, False, 0)
        page.pack_start(_row("Model", self.f_or_model,
                             "Model id as the endpoint expects it."),
                        False, False, 0)
        page.pack_start(_row("Temperature", self.f_or_temp,
                             "0.0–1.0. Lower = more literal cleanup."),
                        False, False, 0)
        test_btn = Gtk.Button(label="Test cleaning endpoint")
        test_btn.connect("clicked", self._on_test_clean)
        page.pack_start(test_btn, False, False, 0)
        page.pack_start(Gtk.Label(
            label="Tip: one profile per endpoint (e.g. “Local”, “Remote GPU”, "
                  "“Cloud”). Custom wording lives on the Prompt tab.",
            xalign=0, wrap=True), False, False, 0)

    def _clean_fields(self):
        try:
            float(self.f_or_temp.get_text().strip() or 0.1)
            temp = self.f_or_temp.get_text().strip() or "0.1"
        except ValueError:
            temp = "0.1"
        return {
            "OMNIROUTE_BASE_URL": self.f_or_url.get_text().strip()
            or "http://127.0.0.1:20128",
            "OMNIROUTE_API_KEY": self.f_or_key.get_text().strip(),
            "OMNIROUTE_MODEL": self.f_or_model.get_text().strip() or "auto",
            "CLEANING_TEMPERATURE": temp,
        }

    def _fill_clean(self, prof):
        self.f_or_url.set_text(prof.get("OMNIROUTE_BASE_URL", ""))
        self.f_or_key.set_text(prof.get("OMNIROUTE_API_KEY", ""))
        self.f_or_model.set_text(prof.get("OMNIROUTE_MODEL", "auto"))
        self.f_or_temp.set_text(prof.get("CLEANING_TEMPERATURE", "0.1"))

    def _on_clean_select(self, combo):
        prof = self.profiles["clean_profiles"].get(self._combo_value(combo))
        if prof:
            self._fill_clean(prof)

    def _on_clean_save(self, _btn, name=None):
        name = name or self._combo_value(self.clean_combo)
        if not name:
            return
        self.profiles["clean_profiles"][name] = self._clean_fields()
        self.profiles["active_clean"] = name
        store.save_profiles(self.profiles)
        store.save_env(self._clean_fields())
        self._refresh_combo(self.clean_combo,
                            list(self.profiles["clean_profiles"]), name)
        self.say(f"Cleaning profile “{name}” saved. Restart daemon to apply.")

    def _on_clean_delete(self, _btn):
        name = self._combo_value(self.clean_combo)
        if len(self.profiles["clean_profiles"]) <= 1:
            self.say("Cannot delete the last cleaning profile.")
            return
        self.profiles["clean_profiles"].pop(name, None)
        new_active = list(self.profiles["clean_profiles"])[0]
        self.profiles["active_clean"] = new_active
        store.save_profiles(self.profiles)
        self._refresh_combo(self.clean_combo,
                            list(self.profiles["clean_profiles"]), new_active)
        self._fill_clean(self.profiles["clean_profiles"][new_active])
        self.say(f"Deleted “{name}”. Active: “{new_active}”.")

    def _on_test_clean(self, _btn):
        self.say("Testing cleaning endpoint…")

        def _work():
            from llm.omniroute import OmniRouteProcessor
            f = self._clean_fields()
            try:
                proc = OmniRouteProcessor(
                    base_url=f["OMNIROUTE_BASE_URL"],
                    api_key=f["OMNIROUTE_API_KEY"],
                    model=f["OMNIROUTE_MODEL"],
                    temperature=float(f["CLEANING_TEMPERATURE"]))
                out = proc.process("hello world this is a test",
                                   system_prompt="Reply with exactly: OK")
                self.say(f"Endpoint OK — replied: {out[:80]}")
            except Exception as exc:
                self.say(f"Endpoint failed: {exc}")
        self.run_bg(_work)

    # -- Tab 3: Prompt ----------------------------------------------------
    def _build_prompt_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)
        self.nb.append_page(page, Gtk.Label(label="Prompt"))

        self.use_custom = Gtk.CheckButton(
            label="Use custom cleaning prompt (instead of built-in)")
        self.use_custom.set_active(
            self.env.get("USE_CUSTOM_PROMPT", "false").lower()
            in ("1", "true", "yes"))
        page.pack_start(self.use_custom, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        buf = self.prompt_view.get_buffer()
        custom = store.load_custom_prompt()
        buf.set_text(custom if custom.strip() else SYSTEM_PROMPT)
        scrolled.add(self.prompt_view)
        page.pack_start(scrolled, True, True, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_btn = Gtk.Button(label="Save prompt")
        save_btn.connect("clicked", self._on_prompt_save)
        row.pack_start(save_btn, False, False, 0)
        reset_btn = Gtk.Button(label="Reset to built-in default")
        reset_btn.connect("clicked", self._on_prompt_reset)
        row.pack_start(reset_btn, False, False, 0)
        page.pack_start(row, False, False, 0)
        page.pack_start(Gtk.Label(
            label="Used for Clean mode (and as the base for Smart mode). "
                  "Raw mode always skips the LLM. "
                  "Your vocabulary terms are appended automatically.",
            xalign=0, wrap=True), False, False, 0)

    def _on_prompt_save(self, _btn):
        buf = self.prompt_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        store.save_custom_prompt(text)
        enabled = "true" if self.use_custom.get_active() else "false"
        store.save_env({"USE_CUSTOM_PROMPT": enabled})
        self.say("Prompt saved. Restart daemon (or next utterance) to apply.")

    def _on_prompt_reset(self, _btn):
        self.prompt_view.get_buffer().set_text(SYSTEM_PROMPT)
        self.say("Reset to built-in default (press Save prompt to keep it).")

    # -- Tab 4: Mode & Voice ----------------------------------------------
    def _build_mode_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)
        self.nb.append_page(page, Gtk.Label(label="Mode & Voice"))

        page.pack_start(Gtk.Label(label="Processing mode", xalign=0),
                        False, False, 0)
        self.mode_radios = {}
        first = None
        mode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for mode, desc in (("raw", "Raw — paste verbatim, vocab casing only"),
                           ("clean", "Clean — tidy up (default)"),
                           ("smart", "Smart — adapt style to the active app"),
                           ("professional", "Professional — formal, full forms"),
                           ("casual", "Casual — conversational, contractions OK"),
                           ("email", "Email — greeting / body / closing"),
                           ("chat", "Chat — short + casual"),
                           ("code", "Code — literal identifiers")):
            r = Gtk.RadioButton.new_with_label_from_widget(first, f"{desc}")
            if first is None:
                first = r
            self.mode_radios[mode] = r
            mode_box.pack_start(r, False, False, 0)
        cur_mode = self.env.get("PROCESSING_MODE", "clean")
        if cur_mode in self.mode_radios:
            self.mode_radios[cur_mode].set_active(True)
        page.pack_start(mode_box, False, False, 0)

        self.f_prefix = _entry(self.env.get("COMMAND_PREFIX", "computer"))
        page.pack_start(_row("Voice command prefix", self.f_prefix,
                             'Say "<prefix> cancel" to discard, '
                             '"<prefix> raw …" for a one-shot mode.'),
                        False, False, 0)
        self.f_save_rec = Gtk.CheckButton(
            label="Keep WAV copy of every utterance (debug)")
        self.f_save_rec.set_active(
            self.env.get("SAVE_RECORDINGS", "false").lower()
            in ("1", "true", "yes"))
        page.pack_start(self.f_save_rec, False, False, 0)

        page.pack_start(Gtk.Label(label="Vocabulary (one exact term per line)",
                                   xalign=0), False, False, 0)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.vocab_view = Gtk.TextView()
        self.vocab_view.get_buffer().set_text(
            "\n".join(store.load_vocabulary()))
        scrolled.add(self.vocab_view)
        page.pack_start(scrolled, True, True, 0)
        save_btn = Gtk.Button(label="Save mode & voice settings")
        save_btn.connect("clicked", self._on_mode_save)
        page.pack_start(save_btn, False, False, 0)

    def _on_mode_save(self, _btn):
        mode = next((m for m, r in self.mode_radios.items()
                     if r.get_active()), "clean")
        buf = self.vocab_view.get_buffer()
        terms = [t.strip() for t in buf.get_text(
            buf.get_start_iter(), buf.get_end_iter(), True).splitlines()
            if t.strip()]
        store.save_vocabulary(terms)
        store.save_env({
            "PROCESSING_MODE": mode,
            "COMMAND_PREFIX": self.f_prefix.get_text().strip() or "computer",
            "SAVE_RECORDINGS": "true" if self.f_save_rec.get_active()
            else "false",
        })
        self.say(f"Saved (mode={mode}, {len(terms)} vocabulary terms).")

    # -- Tab 5: Microphone -------------------------------------------------
    def _build_mic_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)
        self.nb.append_page(page, Gtk.Label(label="Microphone"))

        page.pack_start(Gtk.Label(
            label="Why Bluetooth headsets stay silent: (1) they connect in "
                  "A2DP (music, output-only) with no mic — switch to HSP/HFP "
                  "below for voice; (2) on some headsets the HD voice codec "
                  "(mSBC) fails to decode — the voice button detects that and "
                  "falls back to CVSD automatically.",
            xalign=0, wrap=True), False, False, 0)

        self.bt_status = Gtk.Label(label="Bluetooth status: …", xalign=0)
        self.bt_status.set_line_wrap(True)
        self.bt_status.set_selectable(True)
        page.pack_start(self.bt_status, False, False, 0)

        bt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        voice_btn = Gtk.Button(label="Headset → voice (auto)")
        voice_btn.set_tooltip_text(
            "Tries HD voice (mSBC), verifies decoding, falls back to "
            "compatible voice (CVSD) if mSBC is broken. Recommended.")
        voice_btn.connect("clicked", self._on_bt_voice)
        bt_row.pack_start(voice_btn, False, False, 0)
        cvsd_btn = Gtk.Button(label="Headset → voice (CVSD)")
        cvsd_btn.set_tooltip_text(
            "Force compatible 8 kHz voice codec directly (skips the mSBC "
            "check). Use if auto mode misbehaves.")
        cvsd_btn.connect("clicked", self._on_bt_voice_cvsd)
        bt_row.pack_start(cvsd_btn, False, False, 0)
        music_btn = Gtk.Button(label="Headset → music (A2DP)")
        music_btn.connect("clicked", self._on_bt_music)
        bt_row.pack_start(music_btn, False, False, 0)
        bt_refresh = Gtk.Button(label="Refresh")
        bt_refresh.connect("clicked", lambda *_: self.refresh_mic_lists())
        bt_row.pack_start(bt_refresh, False, False, 0)
        page.pack_start(bt_row, False, False, 0)

        page.pack_start(Gtk.Label(label="Input device for AutoType", xalign=0),
                        False, False, 0)
        dev_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.mic_combo = Gtk.ComboBoxText()
        dev_row.pack_start(self.mic_combo, True, True, 0)
        use_btn = Gtk.Button(label="Use selected")
        use_btn.connect("clicked", self._on_mic_use)
        dev_row.pack_start(use_btn, False, False, 0)
        page.pack_start(dev_row, True, False, 0)

        self.mic_entry = _entry(self.env.get("MIC_DEVICE", ""),
                                placeholder="(empty = follow system, recommended)")
        page.pack_start(_row("MIC_DEVICE value", self.mic_entry,
                             "Empty (recommended) = follow PipeWire's default "
                             "source, so Internal/BT switches just work. Or a "
                             "name part (pipewire, Buds, Built-in) or index."),
                        False, False, 0)

        test_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        test_btn = Gtk.Button(label="Test mic (3 s — speak now)")
        test_btn.connect("clicked", self._on_mic_test)
        test_row.pack_start(test_btn, False, False, 0)
        self.mic_result = Gtk.Label(label="", xalign=0)
        test_row.pack_start(self.mic_result, True, True, 0)
        page.pack_start(test_row, False, False, 0)

        save_btn = Gtk.Button(label="Save microphone setting")
        save_btn.connect("clicked", self._on_mic_save)
        page.pack_start(save_btn, False, False, 0)

        self.refresh_mic_lists()

    def refresh_mic_lists(self):
        def _work():
            from audio import devices as dev
            try:
                inputs = dev.list_input_devices()
            except Exception:
                inputs = []
            try:
                cards = dev.list_bt_cards()
            except Exception:
                cards = []
            try:
                ready, msg = dev.bt_voice_ready()
            except Exception as exc:
                ready, msg = False, str(exc)

            try:
                diag = dev.route_diagnosis()
            except Exception as exc:
                diag = {"error": str(exc)}

            def _ui():
                self.mic_combo.remove_all()
                self.mic_combo.append_text(
                    "(follow system via pipewire)  —  leave MIC_DEVICE empty")
                for d in inputs:
                    tags = []
                    if d.get("is_pipewire"):
                        tags.append("recommended")
                    if d.get("bluetooth_hint"):
                        tags.append("BT?")
                    mark = f"  [{','.join(tags)}]" if tags else ""
                    self.mic_combo.append_text(
                        f"{d['index']}: {d['name']}{mark}")
                self.mic_combo.set_active(0)
                lines = []
                if cards:
                    info = "; ".join(
                        f"{c.get('alias') or c['name']}: "
                        f"{c.get('active_profile') or '?'}"
                        for c in cards)
                    lines.append(f"Bluetooth: {info}")
                    lines.append(msg)
                else:
                    lines.append("Bluetooth: no BT audio card in PipeWire. "
                                 + msg)
                lines.append(
                    f"App records from: {diag.get('resolved')} "
                    f"(MIC_DEVICE={diag.get('mic_setting')}); "
                    f"pinned to source: "
                    f"{diag.get('capture_target') or '(auto)'}; "
                    f"system default source: "
                    f"{diag.get('default_source') or '?'}; "
                    f"BT codec: {diag.get('codec') or '-'}; "
                    f"decoder errors (10 min): "
                    f"{diag.get('sbc_errors_10min')}")
                if (diag.get("sbc_errors_10min") or 0) > 0:
                    lines.append("mSBC decoding is failing — use the voice "
                                 "(auto) button to fall back to CVSD.")
                self.bt_status.set_text("\n".join(lines))
                return False
            GLib.idle_add(_ui)
        self.run_bg(_work)

    def _on_bt_voice(self, _btn):
        self.say("Switching headset to voice… trying mSBC, verifying… "
                 "(takes ~5 s)")

        def _work():
            from audio import devices as dev
            try:
                card, prof, note = dev.switch_bt_for_voice()
                self.say(f"Headset voice ready: {prof} ({card}). {note} "
                         "Now run the mic test while speaking.")
            except Exception as exc:
                self.say(f"Voice switch failed: {exc}")
            self.refresh_mic_lists()
        self.run_bg(_work)

    def _on_bt_voice_cvsd(self, _btn):
        self.say("Switching headset to voice (CVSD)…")

        def _work():
            from audio import devices as dev
            try:
                card, prof, note = dev.switch_bt_for_voice(prefer="cvsd",
                                                           verify=False)
                self.say(f"Headset voice ready: {prof} ({card}). {note} "
                         "Now run the mic test while speaking.")
            except Exception as exc:
                self.say(f"Voice switch failed: {exc}")
            self.refresh_mic_lists()
        self.run_bg(_work)

    def _on_bt_music(self, _btn):
        self.say("Switching headset to A2DP…")

        def _work():
            from audio import devices as dev
            try:
                card, prof = dev.switch_bt_for_music()
                self.say(f"Headset on music profile: {prof} ({card}). "
                         "Note: the headset mic is unavailable in A2DP.")
            except Exception as exc:
                self.say(f"Profile switch failed: {exc}")
            self.refresh_mic_lists()
        self.run_bg(_work)

    def _on_mic_use(self, _btn):
        text = self._combo_value(self.mic_combo)
        if text.startswith("(follow system)"):
            self.mic_entry.set_text("")
        else:
            idx = text.split(":")[0].strip()
            # Prefer a human-readable substring over a bare index when
            # the name looks stable (survives BT reconnects better).
            name = text.split(":", 1)[1].strip()
            hint = ""
            for key in ("pipewire", "Buds", "Headset", "Handsfree",
                        "Built-in", "default"):
                if key.lower() in (name + " " + text).lower():
                    hint = key
                    break
            self.mic_entry.set_text(hint or idx)

    def _on_mic_save(self, _btn):
        store.save_env({"MIC_DEVICE": self.mic_entry.get_text().strip()})
        self.say("Microphone saved. Restart daemon to apply.")

    def _on_mic_test(self, _btn):
        self.mic_result.set_text("Recording 3 s — speak now…")

        def _work():
            from audio import devices as dev
            pref = self.mic_entry.get_text().strip()
            try:
                res = dev.quick_test(dev.resolve_mic_device(pref), seconds=3.0)
                GLib.idle_add(self.mic_result.set_text,
                              f"OK: peak {res['peak']} rms {res['rms']} "
                              f"(device {res['device']})")
                self.say("Mic test OK — levels look good.")
            except Exception as exc:
                GLib.idle_add(self.mic_result.set_text, f"FAILED: {exc}")
                self.say(f"Mic test failed: {exc}")
        self.run_bg(_work)

    # -- Tab 6: General ----------------------------------------------------
    def _build_general_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)
        self.nb.append_page(page, Gtk.Label(label="General"))

        page.pack_start(Gtk.Label(
            label="Hotkey: double-tap Right Alt to start/stop. "
                  "Voice commands: “<prefix> cancel”, “<prefix> raw/clean/smart/professional/casual/email/chat/code …”. "
                  "Speech helpers: say “comma / period / question mark / new paragraph / new line / bullet point / numbered list …” — applied before the LLM.",
            xalign=0, wrap=True), False, False, 0)
        self.daemon_label = Gtk.Label(label="Daemon: …", xalign=0)
        page.pack_start(self.daemon_label, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for label, fn in (("Status", self._update_daemon_status),
                          ("Start", self._on_daemon_start),
                          ("Stop", self._on_daemon_stop),
                          ("Restart", self._on_restart_daemon)):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            row.pack_start(b, False, False, 0)
        page.pack_start(row, False, False, 0)

        page.pack_start(Gtk.Label(label="Recent log", xalign=0),
                        False, False, 0)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        scrolled.add(self.log_view)
        page.pack_start(scrolled, True, True, 0)
        log_btn = Gtk.Button(label="Refresh log")
        log_btn.connect("clicked", lambda *_: self._update_daemon_status())
        page.pack_start(log_btn, False, False, 0)
        self._update_daemon_status()

    def _daemon_pid(self):
        """PID from data/daemon.pid if that process is still our daemon."""
        try:
            pid = int((BASE_DIR / "data" / "daemon.pid").read_text().strip())
        except Exception:
            return None
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().decode(errors="replace")
            # Verify it's really ours: cmdline mentions app.py and the
            # process cwd is this project.
            cwd = str(Path(f"/proc/{pid}/cwd").resolve())
            if "app.py" in cmd and cwd == str(BASE_DIR):
                return pid
        except Exception:
            pass
        return None

    def _daemon_running(self):
        if self._daemon_pid() is not None:
            return True
        # Fallback: any python running app.py from this project dir.
        try:
            out = subprocess.run(["pgrep", "-af", "python.*app\\.py"],
                                 capture_output=True, text=True,
                                 timeout=5)
            return bool(out.stdout.strip())
        except Exception:
            return False

    def _stop_daemon_processes(self):
        pid = self._daemon_pid()
        if pid is not None:
            try:
                subprocess.run(["kill", str(pid)], capture_output=True,
                               timeout=5)
                return
            except Exception:
                pass
        # Fallback for daemons started before the pidfile existed.
        subprocess.run(["pkill", "-f", "autotype.*app\\.py"],
                       capture_output=True, timeout=5)
        subprocess.run(["bash", "-c",
                        "for p in $(pgrep -f 'python app\\.py'); do "
                        "if [ \"$(readlink /proc/$p/cwd)\" "
                        "= \"" + str(BASE_DIR) + "\" ]; then kill $p; fi; done"],
                       capture_output=True, timeout=5)

    def _update_daemon_status(self, _btn=None):
        running = self._daemon_running()
        self.daemon_label.set_text(
            "Daemon: RUNNING (double-tap Right Alt to dictate)"
            if running else "Daemon: STOPPED")
        # tail the newest log
        try:
            logdir = BASE_DIR / "logs"
            logs = sorted(logdir.glob("*.log"),
                          key=lambda p: p.stat().st_mtime) if logdir.exists() \
                else []
            text = ""
            if logs:
                text = logs[-1].read_text(encoding="utf-8",
                                          errors="replace")[-6000:]
            self.log_view.get_buffer().set_text(
                text or "(no logs yet)")
        except Exception as exc:
            self.log_view.get_buffer().set_text(f"(log read failed: {exc})")

    def _on_daemon_start(self, _btn):
        def _work():
            try:
                subprocess.Popen(
                    [sys.executable, str(BASE_DIR / "app.py")],
                    cwd=str(BASE_DIR),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
                self.say("Daemon starting…")
            except Exception as exc:
                self.say(f"Start failed: {exc}")
            GLib.idle_add(self._update_daemon_status)
        self.run_bg(_work)

    def _on_daemon_stop(self, _btn):
        def _work():
            self._stop_daemon_processes()
            self.say("Daemon stopped.")
            GLib.idle_add(self._update_daemon_status)
        self.run_bg(_work)

    def _on_restart_daemon(self, _btn):
        def _work():
            self._stop_daemon_processes()
            import time
            time.sleep(1.0)
            try:
                subprocess.Popen(
                    [sys.executable, str(BASE_DIR / "app.py")],
                    cwd=str(BASE_DIR),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
                self.say("Daemon restarted with new settings.")
            except Exception as exc:
                self.say(f"Restart failed: {exc}")
            GLib.idle_add(self._update_daemon_status)
        self.run_bg(_work)


def main():
    win = SettingsWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
