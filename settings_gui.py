#!/usr/bin/env python3
"""AutoType Settings — GNOME HIG-style preferences window (GTK3 + libhandy).

Structure: HdyPreferencesWindow with pages of grouped rounded cards
(HdyPreferencesGroup). One setting per row — HdyActionRow with a short
title, optional explanatory subtitle, and a right-aligned control.
Rarely-used options live inside HdyExpanderRow sections so the main
page stays uncluttered.

Pages: General | Speech | Cleaning | Microphone | Advanced.

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
gi.require_version("Handy", "1")
from gi.repository import GLib, Gtk, Handy  # noqa: E402

Handy.init()

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from llm.processor import LLMProcessor, PROVIDER_CONFIGS, normalize_provider  # noqa: E402
from llm.prompts import SYSTEM_PROMPT  # noqa: E402
from ui import settings_store as store  # noqa: E402


# -- row-building helpers ---------------------------------------------------

def _switch_row(title, subtitle=None, active=False):
    """Action row with a right-aligned GtkSwitch; row click toggles."""
    row = Handy.ActionRow()
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    switch = Gtk.Switch()
    switch.set_valign(Gtk.Align.CENTER)
    switch.set_active(active)
    row.add(switch)  # ActionRow.add() places the control right-aligned
    row.set_activatable_widget(switch)
    row.switch = switch
    return row


def _entry_row(title, text="", secret=False, placeholder="", tooltip=None):
    """Action row with a right-aligned text entry."""
    row = Handy.ActionRow()
    row.set_title(title)
    entry = Gtk.Entry()
    entry.set_valign(Gtk.Align.CENTER)
    entry.set_hexpand(True)
    entry.set_text(text or "")
    entry.set_visibility(not secret)
    if placeholder:
        entry.set_placeholder_text(placeholder)
    if tooltip:
        row.set_tooltip_text(tooltip)
    row.add(entry)
    row.entry = entry
    return row


def _combo_row(title, items, active_index=0, subtitle=None, tooltip=None):
    """Action row with a right-aligned dropdown."""
    row = Handy.ActionRow()
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    combo = Gtk.ComboBoxText()
    combo.set_valign(Gtk.Align.CENTER)
    for item in items:
        combo.append_text(item)
    combo.set_active(active_index)
    if tooltip:
        row.set_tooltip_text(tooltip)
    row.add(combo)
    row.combo = combo
    return row


def _button_row(title, subtitle=None):
    """Action row that acts like a button (whole row clickable)."""
    row = Handy.ActionRow()
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    arrow = Gtk.Image.new_from_icon_name("go-next-symbolic",
                                        Gtk.IconSize.BUTTON)
    arrow.set_valign(Gtk.Align.CENTER)
    row.add(arrow)
    row.set_activatable(True)
    return row


class SettingsWindow(Handy.PreferencesWindow):
    def __init__(self):
        super().__init__()
        self.set_title("AutoType Settings")
        self.set_default_size(640, 576)
        self.set_search_enabled(True)

        self.env = store.load_env()
        self.profiles = store.load_profiles()

        self._build_general_page()
        self._build_speech_page()
        self._build_cleaning_page()
        self._build_mic_page()
        self._build_advanced_page()

    # -- helpers ---------------------------------------------------------
    def say(self, text):
        """Transient status message via desktop notification."""
        from desktop import notifications
        notifications.notify("AutoType", text)

    def run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _page(self, title, icon):
        page = Handy.PreferencesPage()
        page.set_title(title)
        page.set_icon_name(icon)
        self.add(page)
        return page

    def _group(self, page, title, description=None):
        group = Handy.PreferencesGroup()
        group.set_title(title)
        if description:
            group.set_description(description)
        page.add(group)
        return group

    # -- Page: General -----------------------------------------------------
    def _build_general_page(self):
        page = self._page("General", "preferences-system-symbolic")

        group = self._group(
            page, "Behavior",
            "How AutoType processes what you dictate.")
        self._build_mode_section(group)

        group = self._group(
            page, "Vocabulary",
            "Terms AutoType should spell exactly as written.")
        self._build_vocab_section(group)

        group = self._group(page, "Daemon",
                             "The background process that listens for speech.")
        self._build_daemon_section(group)

    def _build_mode_section(self, group):
        MODES = (
            ("clean", "Clean",
             "Tidy up dictation — remove filler, fix punctuation. Default."),
            ("smart", "Smart",
             "Adapt the style to the active application."),
            ("raw", "Raw",
             "Paste exactly what was heard; vocabulary casing only."),
            ("professional", "Professional",
             "Formal tone, full forms, no contractions."),
            ("casual", "Casual",
             "Conversational tone, contractions are fine."),
            ("email", "Email",
             "Structured greeting, body, and closing."),
            ("chat", "Chat",
             "Short and casual messages."),
            ("code", "Code",
             "Literal identifiers and code symbols."),
        )
        labels = [label for _, label, _ in MODES]
        cur_mode = self.env.get("PROCESSING_MODE", "clean")
        mode_keys = [key for key, _, _ in MODES]
        try:
            active = mode_keys.index(cur_mode)
        except ValueError:
            active = 0
        self.mode_row = _combo_row(
            "Processing Mode", labels, active,
            subtitle="Say “computer clean/raw/smart …” to switch by voice.")
        self.mode_row.combo.connect("changed", self._on_mode_changed)
        group.add(self.mode_row)

        self.prefix_row = _entry_row(
            "Voice Command Prefix", self.env.get("COMMAND_PREFIX", "computer"),
            tooltip='Say "<prefix> cancel" to discard, "<prefix> raw …" '
                    "for a one-shot mode.")
        group.add(self.prefix_row)

        self.save_rec_row = _switch_row(
            "Keep Recordings",
            "Save a WAV copy of every utterance for debugging.",
            self.env.get("SAVE_RECORDINGS", "false").lower()
            in ("1", "true", "yes"))
        self.save_rec_row.switch.connect(
            "notify::active", self._on_save_rec_toggled)
        group.add(self.save_rec_row)

    def _on_mode_changed(self, combo):
        mode = self._combo_value(combo)
        self.prefix_row.entry.set_text(self.prefix_row.entry.get_text().strip()
                                      or "computer")
        store.save_env({
            "PROCESSING_MODE": mode,
            "COMMAND_PREFIX": self.prefix_row.entry.get_text().strip()
            or "computer",
        })
        self.say(f"Processing mode set to {mode}. Restart daemon to apply.")

    def _on_save_rec_toggled(self, switch, _pspec):
        store.save_env({"SAVE_RECORDINGS":
                        "true" if switch.get_active() else "false"})
        self.say("Recording preference saved. Restart daemon to apply.")

    # -- Vocabulary --------------------------------------------------------
    def _build_vocab_section(self, group):
        self.vocab_expander = Handy.ExpanderRow()
        self.vocab_expander.set_title("Edit Vocabulary")
        self.vocab_expander.set_subtitle(
            f"{len(store.load_vocabulary())} terms")
        inner = Handy.ActionRow()
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(160)
        scrolled.set_min_content_width(460)
        self.vocab_view = Gtk.TextView()
        self.vocab_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.vocab_view.get_buffer().set_text(
            "\n".join(store.load_vocabulary()))
        scrolled.add(self.vocab_view)
        inner.add(scrolled)
        self.vocab_expander.add(inner)
        group.add(self.vocab_expander)

        save_btn = Gtk.Button(label="Save Vocabulary")
        save_btn.set_halign(Gtk.Align.CENTER)
        save_btn.connect("clicked", self._on_vocab_save)
        group.add(save_btn)

    def _on_vocab_save(self, _btn):
        buf = self.vocab_view.get_buffer()
        terms = [t.strip() for t in buf.get_text(
            buf.get_start_iter(), buf.get_end_iter(), True).splitlines()
            if t.strip()]
        store.save_vocabulary(terms)
        self.vocab_expander.set_subtitle(f"{len(terms)} terms")
        self.say(f"Saved {len(terms)} vocabulary terms.")

    # -- Daemon ------------------------------------------------------------
    def _build_daemon_section(self, group):
        self.daemon_row = _button_row("Daemon Status", "Checking…")
        self.daemon_row.connect("activated", self._update_daemon_status)
        group.add(self.daemon_row)

        for title, fn in (("Restart Daemon", self._on_restart_daemon),):
            row = _button_row(title)
            row.connect("activated", fn)
            group.add(row)

    # -- Page: Speech ------------------------------------------------------
    def _build_speech_page(self):
        page = self._page("Speech", "audio-input-microphone-symbolic")

        group = self._group(
            page, "Speech-to-Text Engine",
            "Choose a Cloud STT provider or run 100% offline locally.")
        self._build_stt_section(group)

    def _build_stt_section(self, group):
        names = list(self.profiles["stt_profiles"])
        active_name = self.profiles.get("active_stt", names[0])
        try:
            active_idx = names.index(active_name)
        except ValueError:
            active_idx = 0
        self.stt_profile_row = _combo_row(
            "Profile Preset", names, active_idx,
            subtitle="Quick presets for Cloud and Local offline setups.")
        self.stt_profile_row.combo.connect("changed", self._on_stt_select)
        group.add(self.stt_profile_row)

        cur = self.profiles["stt_profiles"][
            self._combo_value(self.stt_profile_row.combo)]

        # STT Category: Cloud vs Local
        cat_labels = ["Cloud STT (Online API)", "Local STT (100% Offline)"]
        is_local = cur.get("STT_TYPE") == "local" or cur.get("STT_BACKEND") in ("parakeet", "parakeet_stream")
        self.stt_category_row = _combo_row(
            "Engine Category", cat_labels, 1 if is_local else 0,
            subtitle="Cloud sends audio to an API; Local runs fully on-device without internet.")
        self.stt_category_row.combo.connect("changed", self._on_stt_category_changed)
        group.add(self.stt_category_row)

        # -- Cloud STT Section --
        self.cloud_stt_expander = Handy.ExpanderRow()
        self.cloud_stt_expander.set_title("Cloud Speech-to-Text Providers")
        self.cloud_stt_expander.set_subtitle("Deepgram, OpenAI Whisper, Groq, NVIDIA NIM, or Custom")

        cloud_prov_labels = [
            "Deepgram (Streaming & Batch)",
            "OpenAI Whisper Cloud",
            "Groq Whisper Cloud (Ultra-fast)",
            "NVIDIA NIM Cloud ASR",
            "Custom Cloud STT (OpenAI-compatible)",
        ]
        self.cloud_provider_row = _combo_row(
            "Cloud Provider", cloud_prov_labels, 0,
            subtitle="Select your cloud transcription provider.")
        self.cloud_provider_row.combo.connect("changed", self._on_cloud_provider_changed)
        self.cloud_stt_expander.add(self.cloud_provider_row)

        # Deepgram fields
        self.dg_sub_expander = Handy.ExpanderRow()
        self.dg_sub_expander.set_title("Deepgram Settings")
        self.dg_sub_expander.set_subtitle("Flux streaming & Nova-3 batch")
        self.f_dg_key = _entry_row("Deepgram API Key", cur.get("DEEPGRAM_API_KEY"), secret=True)
        self.f_dg_model = _entry_row("Batch Model", cur.get("DEEPGRAM_MODEL", "nova-3"), placeholder="nova-3")
        self.f_dg_lang = _entry_row("Language", cur.get("DEEPGRAM_LANGUAGE", "en-US"), placeholder="en-US")
        self.f_dg_flux = _entry_row("Flux Stream Model", cur.get("DEEPGRAM_FLUX_MODEL", "flux-general-en"), placeholder="flux-general-en")
        for r in (self.f_dg_key, self.f_dg_model, self.f_dg_lang, self.f_dg_flux):
            self.dg_sub_expander.add(r)
        self.cloud_stt_expander.add(self.dg_sub_expander)

        # Generic Cloud STT fields (Whisper, Groq, NVIDIA, Custom)
        self.cloud_generic_expander = Handy.ExpanderRow()
        self.cloud_generic_expander.set_title("OpenAI / Whisper / NVIDIA Cloud Settings")
        self.cloud_generic_expander.set_subtitle("OpenAI-compatible audio/transcriptions endpoint")
        self.f_cloud_key = _entry_row("API Key", cur.get("CLOUD_STT_API_KEY"), secret=True)
        self.f_cloud_url = _entry_row("Base URL", cur.get("CLOUD_STT_BASE_URL", "https://api.openai.com/v1"), placeholder="https://api.openai.com/v1")
        self.f_cloud_model = _entry_row("Model", cur.get("CLOUD_STT_MODEL", "whisper-1"), placeholder="whisper-1")
        self.f_cloud_lang = _entry_row("Language", cur.get("CLOUD_STT_LANGUAGE", "en"), placeholder="en")
        for r in (self.f_cloud_key, self.f_cloud_url, self.f_cloud_model, self.f_cloud_lang):
            self.cloud_generic_expander.add(r)
        self.cloud_stt_expander.add(self.cloud_generic_expander)

        group.add(self.cloud_stt_expander)

        # -- Local STT Section --
        self.local_stt_expander = Handy.ExpanderRow()
        self.local_stt_expander.set_title("Local Speech-to-Text (Offline)")
        self.local_stt_expander.set_subtitle("On-device transcription via Parakeet")

        local_eng_labels = [
            "Parakeet Stream (120M EOU — Real-time)",
            "Parakeet Batch (transcribe-cli 0.6B)",
        ]
        self.local_backend_row = _combo_row(
            "Local Engine", local_eng_labels, 0,
            subtitle="Streaming transcribes live; Batch transcribes after stopping.")
        self.local_backend_row.combo.connect("changed", self._on_local_engine_changed)
        self.local_stt_expander.add(self.local_backend_row)

        self.f_pks_bin = _entry_row("Stream Binary", cur.get("PARAKEET_STREAM_BINARY"))
        self.f_pks_model = _entry_row("Stream Model", cur.get("PARAKEET_STREAM_MODEL"))
        self.f_pk_bin = _entry_row("Batch Binary", cur.get("PARAKEET_BINARY"))
        self.f_pk_model = _entry_row("Batch Model", cur.get("PARAKEET_MODEL"))
        for r in (self.f_pks_bin, self.f_pks_model, self.f_pk_bin, self.f_pk_model):
            self.local_stt_expander.add(r)

        group.add(self.local_stt_expander)

        # Action buttons
        save_stt_row = _button_row(
            "Save STT Settings",
            "Save and set current STT engine as the active persistent default.")
        save_stt_row.connect("activated", self._on_stt_save)
        group.add(save_stt_row)

        test_row = _button_row("Test STT Connection / Files", "Verify API key or local binary/model files.")
        test_row.connect("activated", self._on_test_stt)
        group.add(test_row)

        reset_stt_row = _button_row(
            "Reset STT to Defaults",
            "Restore factory default STT engine (Deepgram Cloud Streaming).")
        reset_stt_row.connect("activated", self._on_reset_stt)
        group.add(reset_stt_row)

        # Initialize expander visibility
        self._update_stt_visibility()

    def _update_stt_visibility(self):
        cat = self._combo_value(self.stt_category_row.combo)
        is_local = "Local" in cat
        self.cloud_stt_expander.set_expanded(not is_local)
        self.cloud_stt_expander.set_enable_expansion(not is_local)
        self.local_stt_expander.set_expanded(is_local)
        self.local_stt_expander.set_enable_expansion(is_local)

        cloud_prov = self._combo_value(self.cloud_provider_row.combo)
        is_dg = "Deepgram" in cloud_prov
        self.dg_sub_expander.set_expanded(is_dg)
        self.cloud_generic_expander.set_expanded(not is_dg)

    def _on_stt_category_changed(self, _combo):
        self._update_stt_visibility()

    def _on_cloud_provider_changed(self, combo):
        prov = self._combo_value(combo)
        if "OpenAI" in prov:
            self.f_cloud_url.entry.set_text("https://api.openai.com/v1")
            self.f_cloud_model.entry.set_text("whisper-1")
        elif "Groq" in prov:
            self.f_cloud_url.entry.set_text("https://api.groq.com/openai/v1")
            self.f_cloud_model.entry.set_text("whisper-large-v3-turbo")
        elif "NVIDIA" in prov:
            self.f_cloud_url.entry.set_text("https://integrate.api.nvidia.com/v1")
            self.f_cloud_model.entry.set_text("nvidia/parakeet-ctc-1.1b-asr")
        self._update_stt_visibility()

    def _on_local_engine_changed(self, _combo):
        pass

    def _stt_fields(self):
        cat = self._combo_value(self.stt_category_row.combo)
        is_local = "Local" in cat

        if is_local:
            local_eng = self._combo_value(self.local_backend_row.combo)
            backend = "parakeet_stream" if "Stream" in local_eng else "parakeet"
            stt_type = "local"
        else:
            cloud_prov = self._combo_value(self.cloud_provider_row.combo)
            stt_type = "cloud"
            if "Deepgram" in cloud_prov:
                backend = "deepgram"
            elif "Groq" in cloud_prov:
                backend = "groq"
            elif "NVIDIA" in cloud_prov:
                backend = "nvidia"
            elif "Custom" in cloud_prov:
                backend = "custom_cloud"
            else:
                backend = "whisper"

        return {
            "STT_TYPE": stt_type,
            "STT_BACKEND": backend,
            "DEEPGRAM_API_KEY": self.f_dg_key.entry.get_text().strip(),
            "DEEPGRAM_MODEL": self.f_dg_model.entry.get_text().strip() or "nova-3",
            "DEEPGRAM_LANGUAGE": self.f_dg_lang.entry.get_text().strip() or "en-US",
            "DEEPGRAM_FLUX_MODEL": self.f_dg_flux.entry.get_text().strip() or "flux-general-en",
            "CLOUD_STT_API_KEY": self.f_cloud_key.entry.get_text().strip() or self.f_dg_key.entry.get_text().strip(),
            "CLOUD_STT_BASE_URL": self.f_cloud_url.entry.get_text().strip() or "https://api.openai.com/v1",
            "CLOUD_STT_MODEL": self.f_cloud_model.entry.get_text().strip() or "whisper-1",
            "CLOUD_STT_LANGUAGE": self.f_cloud_lang.entry.get_text().strip() or "en",
            "PARAKEET_BINARY": self.f_pk_bin.entry.get_text().strip(),
            "PARAKEET_MODEL": self.f_pk_model.entry.get_text().strip(),
            "PARAKEET_STREAM_BINARY": self.f_pks_bin.entry.get_text().strip(),
            "PARAKEET_STREAM_MODEL": self.f_pks_model.entry.get_text().strip(),
        }

    def _fill_stt(self, prof):
        self.f_dg_key.entry.set_text(prof.get("DEEPGRAM_API_KEY", ""))
        self.f_dg_model.entry.set_text(prof.get("DEEPGRAM_MODEL", "nova-3"))
        self.f_dg_lang.entry.set_text(prof.get("DEEPGRAM_LANGUAGE", "en-US"))
        self.f_dg_flux.entry.set_text(prof.get("DEEPGRAM_FLUX_MODEL", "flux-general-en"))
        self.f_cloud_key.entry.set_text(prof.get("CLOUD_STT_API_KEY", ""))
        self.f_cloud_url.entry.set_text(prof.get("CLOUD_STT_BASE_URL", "https://api.openai.com/v1"))
        self.f_cloud_model.entry.set_text(prof.get("CLOUD_STT_MODEL", "whisper-1"))
        self.f_cloud_lang.entry.set_text(prof.get("CLOUD_STT_LANGUAGE", "en"))
        self.f_pk_bin.entry.set_text(prof.get("PARAKEET_BINARY", ""))
        self.f_pk_model.entry.set_text(prof.get("PARAKEET_MODEL", ""))
        self.f_pks_bin.entry.set_text(prof.get("PARAKEET_STREAM_BINARY", ""))
        self.f_pks_model.entry.set_text(prof.get("PARAKEET_STREAM_MODEL", ""))

        backend = prof.get("STT_BACKEND", "deepgram")
        is_local = backend in ("parakeet", "parakeet_stream")
        self.stt_category_row.combo.set_active(1 if is_local else 0)

        if not is_local:
            if backend == "deepgram":
                self.cloud_provider_row.combo.set_active(0)
            elif backend == "whisper" or backend == "openai":
                self.cloud_provider_row.combo.set_active(1)
            elif backend == "groq":
                self.cloud_provider_row.combo.set_active(2)
            elif backend == "nvidia":
                self.cloud_provider_row.combo.set_active(3)
            else:
                self.cloud_provider_row.combo.set_active(4)
        else:
            self.local_backend_row.combo.set_active(0 if backend == "parakeet_stream" else 1)

        self._update_stt_visibility()

    def _on_stt_select(self, combo):
        name = self._combo_value(combo)
        prof = self.profiles["stt_profiles"].get(name)
        if prof:
            self._fill_stt(prof)

    def _on_stt_save(self, _btn=None, name=None):
        name = name or self._combo_value(self.stt_profile_row.combo)
        if not name:
            name = "Active STT"
        fields = self._stt_fields()
        self.profiles["stt_profiles"][name] = dict(fields)
        self.profiles["active_stt"] = name
        store.save_profiles(self.profiles)
        store.save_env(fields)
        self.env.update(fields)
        self._refresh_combo(self.stt_profile_row.combo,
                            list(self.profiles["stt_profiles"]), name)
        self.say(f"STT settings ({fields['STT_BACKEND']}) saved as default. Restart daemon to apply.")

    def _on_reset_stt(self, _row):
        defaults = store.reset_stt_defaults()
        self.env.update(defaults)
        self.profiles = store.load_profiles()
        self._fill_stt(defaults)
        active_name = self.profiles.get("active_stt", "Deepgram (Cloud Streaming)")
        self._refresh_combo(self.stt_profile_row.combo,
                            list(self.profiles["stt_profiles"]), active_name)
        self.say("STT settings reset to factory defaults (Deepgram). Restart daemon to apply.")

    def _on_test_stt(self, _row):
        fields = self._stt_fields()
        backend = fields["STT_BACKEND"]
        if backend == "deepgram":
            self._on_test_dg_key()
        elif backend in ("whisper", "groq", "nvidia", "custom_cloud"):
            self._on_test_cloud_generic(fields)
        else:
            self._on_test_binaries()

    def _on_test_dg_key(self):
        self.say("Testing Deepgram key…")
        key = self.f_dg_key.entry.get_text().strip()

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

    def _on_test_cloud_generic(self, fields):
        self.say(f"Testing Cloud STT ({fields['STT_BACKEND']})…")
        key = fields["CLOUD_STT_API_KEY"]
        url = fields["CLOUD_STT_BASE_URL"]

        def _work():
            import requests
            try:
                headers = {"Authorization": f"Bearer {key}"} if key else {}
                r = requests.get(f"{url.rstrip('/')}/models", headers=headers, timeout=10)
                if r.status_code in (200, 401, 404, 405):
                    self.say(f"Cloud STT endpoint reachable (HTTP {r.status_code}).")
                else:
                    self.say(f"Cloud STT test: HTTP {r.status_code}.")
            except Exception as exc:
                self.say(f"Cloud STT connection test: {exc}")
        self.run_bg(_work)

    def _on_test_binaries(self):
        msgs = []
        for label, path in (("batch binary",
                             self.f_pk_bin.entry.get_text().strip()),
                            ("batch model",
                             self.f_pk_model.entry.get_text().strip()),
                            ("stream binary",
                             self.f_pks_bin.entry.get_text().strip()),
                            ("stream model",
                             self.f_pks_model.entry.get_text().strip())):
            ok = bool(path) and Path(path).exists()
            msgs.append(f"{label}: {'OK' if ok else 'MISSING'}")
        self.say("  •  ".join(msgs))

    # -- Page: Cleaning (LLM) ----------------------------------------------
    def _build_cleaning_page(self):
        page = self._page("Cleaning", "text-editor-symbolic")

        group = self._group(
            page, "LLM Cleaning Provider",
            "Choose any popular AI provider or bring your own API endpoint.")
        self._build_clean_section(group)

        group = self._group(page, "Cleaning Prompt",
                             "Instructions for how text should be tidied.")
        self._build_prompt_section(group)

    def _build_clean_section(self, group):
        self._suppress_clean_changed = True
        try:
            names = list(self.profiles["clean_profiles"])
            active_name = self.profiles.get("active_clean", names[0])
            try:
                active_idx = names.index(active_name)
            except ValueError:
                active_idx = 0
            self.clean_profile_row = _combo_row(
                "Profile Preset", names, active_idx,
                subtitle="Quick presets for popular providers and custom endpoints.")
            self.clean_profile_row.combo.connect("changed", self._on_clean_select)
            group.add(self.clean_profile_row)

            cur = self.profiles["clean_profiles"].get(
                self._combo_value(self.clean_profile_row.combo), {})

            # Providers list
            self.provider_keys = [
                "openai", "anthropic", "xai", "deepseek", "qwen",
                "nvidia", "groq", "openrouter", "ollama", "custom"
            ]
            provider_labels = [
                "OpenAI (ChatGPT)",
                "Anthropic (Claude)",
                "xAI (Grok)",
                "DeepSeek",
                "Qwen (Alibaba DashScope)",
                "NVIDIA NIM",
                "Groq",
                "OpenRouter",
                "Ollama (Local)",
                "Custom API Provider (e.g. OmniRoute)",
            ]

            # Prioritize active .env provider, then profile, then fallback
            cur_prov = (self.env.get("LLM_PROVIDER") or cur.get("LLM_PROVIDER", "openai")).lower()
            try:
                prov_idx = self.provider_keys.index(cur_prov)
            except ValueError:
                prov_idx = self.provider_keys.index("custom") if "custom" in self.provider_keys else 0

            self.clean_provider_row = _combo_row(
                "API Provider", provider_labels, prov_idx,
                subtitle="Select the AI provider you want to use for text cleanup.")
            self.clean_provider_row.combo.connect("changed", self._on_clean_provider_changed)
            group.add(self.clean_provider_row)

            # Prioritize saved values from cur or self.env
            init_url = cur.get("LLM_BASE_URL") or self.env.get("LLM_BASE_URL") or cur.get("OMNIROUTE_BASE_URL") or self.env.get("OMNIROUTE_BASE_URL", "https://api.openai.com/v1")
            init_key = cur.get("LLM_API_KEY") or self.env.get("LLM_API_KEY") or cur.get("OMNIROUTE_API_KEY") or self.env.get("OMNIROUTE_API_KEY", "")
            init_model = cur.get("LLM_MODEL") or self.env.get("LLM_MODEL") or cur.get("OMNIROUTE_MODEL") or self.env.get("OMNIROUTE_MODEL", "gpt-4o-mini")
            init_temp = str(cur.get("CLEANING_TEMPERATURE") or self.env.get("CLEANING_TEMPERATURE", "0.1"))

            self.f_or_url = _entry_row(
                "Base URL", init_url,
                placeholder="https://api.openai.com/v1",
                tooltip="Base API endpoint (OpenAI /chat/completions or Anthropic /messages).")
            self.f_or_key = _entry_row(
                "API Key", init_key,
                secret=True,
                placeholder="API key for selected provider")
            self.f_or_model = _entry_row(
                "Model", init_model,
                placeholder="gpt-4o-mini",
                tooltip="Model identifier expected by the provider.")
            self.f_or_temp = _entry_row(
                "Temperature", init_temp,
                placeholder="0.1",
                tooltip="0.0–1.0. Lower = more faithful cleanup.")

            for r in (self.f_or_url, self.f_or_key, self.f_or_model, self.f_or_temp):
                group.add(r)
        finally:
            self._suppress_clean_changed = False

        save_clean_row = _button_row(
            "Save Cleaning Settings",
            "Save and set current settings as the active persistent default.")
        save_clean_row.connect("activated", self._on_clean_save)
        group.add(save_clean_row)

        test_row = _button_row("Test Cleaning Endpoint", "Sends a short test prompt to verify your key and model.")
        test_row.connect("activated", self._on_test_clean)
        group.add(test_row)

        reset_clean_row = _button_row(
            "Reset Cleaning to Defaults",
            "Restore factory default settings (OpenAI gpt-4o-mini).")
        reset_clean_row.connect("activated", self._on_reset_clean)
        group.add(reset_clean_row)

    def _clean_fields(self):
        try:
            temp = str(float(self.f_or_temp.entry.get_text().strip() or 0.1))
        except ValueError:
            temp = "0.1"

        prov_idx = self.clean_provider_row.combo.get_active()
        prov_key = self.provider_keys[prov_idx] if 0 <= prov_idx < len(self.provider_keys) else "custom"

        url = self.f_or_url.entry.get_text().strip()
        key = self.f_or_key.entry.get_text().strip()
        model = self.f_or_model.entry.get_text().strip()

        return {
            "LLM_PROVIDER": prov_key,
            "LLM_BASE_URL": url,
            "LLM_API_KEY": key,
            "LLM_MODEL": model,
            "CLEANING_TEMPERATURE": temp,
            # Synchronize OMNIROUTE_* for backwards compatibility
            "OMNIROUTE_BASE_URL": url,
            "OMNIROUTE_API_KEY": key,
            "OMNIROUTE_MODEL": model,
        }

    def _fill_clean(self, prof):
        self._suppress_clean_changed = True
        try:
            prov = prof.get("LLM_PROVIDER", "").lower()
            if not prov and (prof.get("OMNIROUTE_BASE_URL") or prof.get("LLM_BASE_URL")):
                prov = "custom"
            elif not prov:
                prov = "openai"

            try:
                idx = self.provider_keys.index(prov)
                self.clean_provider_row.combo.set_active(idx)
            except ValueError:
                self.clean_provider_row.combo.set_active(len(self.provider_keys) - 1)

            url = prof.get("LLM_BASE_URL") or prof.get("OMNIROUTE_BASE_URL", "")
            key = prof.get("LLM_API_KEY") or prof.get("OMNIROUTE_API_KEY", "")
            model = prof.get("LLM_MODEL") or prof.get("OMNIROUTE_MODEL", "")
            temp = str(prof.get("CLEANING_TEMPERATURE", "0.1"))

            self.f_or_url.entry.set_text(url)
            self.f_or_key.entry.set_text(key)
            self.f_or_model.entry.set_text(model)
            self.f_or_temp.entry.set_text(temp)
        finally:
            self._suppress_clean_changed = False

    def _on_clean_select(self, combo):
        prof = self.profiles["clean_profiles"].get(self._combo_value(combo))
        if prof:
            self._fill_clean(prof)

    def _on_clean_provider_changed(self, combo):
        if getattr(self, "_suppress_clean_changed", False):
            return
        idx = combo.get_active()
        if 0 <= idx < len(self.provider_keys):
            prov_key = self.provider_keys[idx]
            if prov_key == "custom":
                custom_prof = self.profiles.get("clean_profiles", {}).get("Custom API Provider", {})
                custom_url = custom_prof.get("LLM_BASE_URL") or self.env.get("LLM_BASE_URL") or self.env.get("OMNIROUTE_BASE_URL") or "http://127.0.0.1:20128/v1"
                custom_model = custom_prof.get("LLM_MODEL") or self.env.get("LLM_MODEL") or self.env.get("OMNIROUTE_MODEL") or "auto"
                custom_key = custom_prof.get("LLM_API_KEY") or self.env.get("LLM_API_KEY") or self.env.get("OMNIROUTE_API_KEY") or ""
                self.f_or_url.entry.set_text(custom_url)
                self.f_or_model.entry.set_text(custom_model)
                self.f_or_key.entry.set_text(custom_key)
                self.f_or_key.entry.set_placeholder_text("API key (optional for local endpoints)")
            else:
                cfg = PROVIDER_CONFIGS.get(prov_key)
                if cfg:
                    prof_name = cfg["name"]
                    saved_prof = self.profiles.get("clean_profiles", {}).get(prof_name, {})
                    self.f_or_url.entry.set_text(saved_prof.get("LLM_BASE_URL") or cfg["base_url"])
                    self.f_or_model.entry.set_text(saved_prof.get("LLM_MODEL") or cfg["default_model"])
                    self.f_or_key.entry.set_text(saved_prof.get("LLM_API_KEY") or "")
                    self.f_or_key.entry.set_placeholder_text(f"API key for {cfg['name']}")

    def _on_clean_save(self, _row=None):
        fields = self._clean_fields()
        prov_key = fields["LLM_PROVIDER"]
        provider_label = self._combo_value(self.clean_provider_row.combo)
        preset_name = self._combo_value(self.clean_profile_row.combo) or "Custom API Provider"

        # Save to both current preset and provider-specific preset
        self.profiles["clean_profiles"][preset_name] = dict(fields)
        if prov_key == "custom":
            self.profiles["clean_profiles"]["Custom API Provider"] = dict(fields)
            self.profiles["active_clean"] = "Custom API Provider"
        else:
            for p_name in self.profiles["clean_profiles"]:
                if prov_key in p_name.lower():
                    self.profiles["clean_profiles"][p_name] = dict(fields)
                    self.profiles["active_clean"] = p_name
                    break
            else:
                self.profiles["active_clean"] = preset_name

        store.save_profiles(self.profiles)
        store.save_env(fields)
        self.env.update(fields)
        self._refresh_combo(self.clean_profile_row.combo,
                            list(self.profiles["clean_profiles"]), self.profiles["active_clean"])
        self.say(f"Cleaning settings saved as default ({provider_label}).")

    def _on_reset_clean(self, _row=None):
        defaults = store.reset_clean_defaults()
        self.env.update(defaults)
        self.profiles = store.load_profiles()
        self._fill_clean(defaults)
        active_name = self.profiles.get("active_clean", "OpenAI (ChatGPT)")
        self._refresh_combo(self.clean_profile_row.combo,
                            list(self.profiles["clean_profiles"]), active_name)
        self.say("Cleaning settings reset to factory defaults (OpenAI).")

    def _on_test_clean(self, _row):
        self.say("Testing cleaning endpoint…")

        def _work():
            f = self._clean_fields()
            try:
                proc = LLMProcessor(
                    base_url=f["LLM_BASE_URL"],
                    api_key=f["LLM_API_KEY"],
                    model=f["LLM_MODEL"],
                    provider=f["LLM_PROVIDER"],
                    temperature=float(f["CLEANING_TEMPERATURE"]),
                )
                out = proc.process(
                    "hello world this is a test",
                    system_prompt="Reply with exactly: OK",
                )
                self.say(f"Endpoint OK — replied: {out[:80]}")
            except Exception as exc:
                self.say(f"Endpoint failed: {exc}")
        self.run_bg(_work)

    # -- Prompt section ----------------------------------------------------
    def _build_prompt_section(self, group):
        self.use_custom_row = _switch_row(
            "Use Custom Cleaning Prompt",
            "Use your own prompt instead of the built-in one.",
            self.env.get("USE_CUSTOM_PROMPT", "false").lower()
            in ("1", "true", "yes"))
        self.use_custom_row.switch.connect(
            "notify::active", self._on_custom_prompt_toggled)
        group.add(self.use_custom_row)

        self.prompt_expander = Handy.ExpanderRow()
        self.prompt_expander.set_title("Edit Prompt")
        self.prompt_expander.set_subtitle("Used for Clean and Smart modes")
        inner = Handy.ActionRow()
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(180)
        scrolled.set_min_content_width(460)
        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        buf = self.prompt_view.get_buffer()
        custom = store.load_custom_prompt()
        buf.set_text(custom if custom.strip() else SYSTEM_PROMPT)
        scrolled.add(self.prompt_view)
        inner.add(scrolled)
        self.prompt_expander.add(inner)
        group.add(self.prompt_expander)

        reset_btn = Gtk.Button(label="Reset to Built-in Default")
        reset_btn.set_halign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_prompt_reset)
        group.add(reset_btn)

    def _on_custom_prompt_toggled(self, switch, _pspec):
        store.save_env({"USE_CUSTOM_PROMPT":
                        "true" if switch.get_active() else "false"})
        self.say("Prompt setting saved.")

    def _on_prompt_reset(self, _btn):
        self.prompt_view.get_buffer().set_text(SYSTEM_PROMPT)
        self.say("Reset to built-in default. "
                 "Use “Test Cleaning Endpoint” after saving.")

    # -- Page: Microphone --------------------------------------------------
    def _build_mic_page(self):
        page = self._page("Microphone", "audio-input-microphone-symbolic")

        group = self._group(page, "Input Device",
                            "What AutoType records from.")
        self._build_mic_section(group)

        group = self._group(page, "Bluetooth Headset",
                            "Switch your headset between voice and music.")
        self._build_bt_section(group)

    def _build_mic_section(self, group):
        self.mic_combo_row = _combo_row(
            "Input Device", ["(follow system)"], 0,
            subtitle="Empty (recommended) follows the system default "
                     "microphone.")
        self.mic_combo_row.combo.connect("changed", self._on_mic_use)
        group.add(self.mic_combo_row)

        self.mic_entry_row = _entry_row(
            "MIC_DEVICE Value", self.env.get("MIC_DEVICE", ""),
            tooltip="Empty (recommended) = follow PipeWire's default source, "
                    "so Internal/BT switches just work. Or a name part "
                    "(pipewire, Buds, Built-in) or index.")
        group.add(self.mic_entry_row)

        test_row = _button_row("Test Microphone",
                               "Records 3 seconds — speak now.")
        test_row.connect("activated", self._on_mic_test)
        group.add(test_row)

        self.refresh_mic_lists()

    def _build_bt_section(self, group):
        self.bt_status_row = Handy.ActionRow()
        self.bt_status_row.set_title("Status")
        self.bt_status_row.set_selectable(False)
        status_label = Gtk.Label(label="Checking…")
        status_label.set_line_wrap(True)
        status_label.set_xalign(0)
        self.bt_status_row.add(status_label)
        self.bt_status_label = status_label
        group.add(self.bt_status_row)

        for title, subtitle, fn in (
                ("Switch to Voice", "Try HD voice (mSBC), fall back to "
                 "compatible voice (CVSD) if broken.",
                 self._on_bt_voice),
                ("Switch to Music (A2DP)", "High-quality audio; the "
                 "headset mic becomes unavailable.",
                 self._on_bt_music),
                ("Refresh", "Re-check devices and Bluetooth status.",
                 self._on_bt_refresh)):
            row = _button_row(title, subtitle)
            row.connect("activated", fn)
            group.add(row)

    def _on_bt_refresh(self, _row):
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
                combo = self.mic_combo_row.combo
                combo.remove_all()
                combo.append_text(
                    "(follow system via pipewire)  —  leave MIC_DEVICE empty")
                for d in inputs:
                    tags = []
                    if d.get("is_pipewire"):
                        tags.append("recommended")
                    if d.get("bluetooth_hint"):
                        tags.append("BT?")
                    mark = f"  [{','.join(tags)}]" if tags else ""
                    combo.append_text(f"{d['index']}: {d['name']}{mark}")
                combo.set_active(0)
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
                    lines.append("mSBC decoding is failing — use Switch to "
                                 "Voice to fall back to CVSD.")
                self.bt_status_label.set_text("\n".join(lines))
                return False
            GLib.idle_add(_ui)
        self.run_bg(_work)

    def _on_bt_voice(self, _row):
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

    def _on_bt_music(self, _row):
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

    def _on_mic_use(self, combo):
        text = self._combo_value(combo)
        if text.startswith("(follow system)"):
            self.mic_entry_row.entry.set_text("")
        else:
            idx = text.split(":")[0].strip()
            name = text.split(":", 1)[1].strip() if ":" in text else text
            hint = ""
            for key in ("pipewire", "Buds", "Headset", "Handsfree",
                        "Built-in", "default"):
                if key.lower() in (name + " " + text).lower():
                    hint = key
                    break
            self.mic_entry_row.entry.set_text(hint or idx)
        store.save_env({"MIC_DEVICE":
                        self.mic_entry_row.entry.get_text().strip()})
        self.say("Microphone saved. Restart daemon to apply.")

    def _on_mic_test(self, _row):
        self.say("Recording 3 s — speak now…")

        def _work():
            from audio import devices as dev
            pref = self.mic_entry_row.entry.get_text().strip()
            try:
                res = dev.quick_test(dev.resolve_mic_device(pref), seconds=3.0)
                self.say(f"Mic test OK: peak {res['peak']} rms {res['rms']} "
                         f"(device {res['device']})")
            except Exception as exc:
                self.say(f"Mic test failed: {exc}")
        self.run_bg(_work)

    # -- Page: Advanced ----------------------------------------------------
    def _build_advanced_page(self):
        page = self._page("Advanced", "emblem-system-symbolic")

        group = self._group(page, "Daemon Log",
                            "Diagnostics from the background process.")
        self.log_expander = Handy.ExpanderRow()
        self.log_expander.set_title("View Recent Log")
        inner = Handy.ActionRow()
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        scrolled.set_min_content_width(460)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        scrolled.add(self.log_view)
        inner.add(scrolled)
        self.log_expander.add(inner)
        group.add(self.log_expander)

        refresh_row = _button_row("Refresh Log")
        refresh_row.connect("activated", lambda row:
                            self._update_daemon_status())
        group.add(refresh_row)

        group = self._group(page, "Shortcuts & Voice Commands")
        info_row = Handy.ActionRow()
        info_row.set_title("How to Use")
        info_row.set_subtitle(
            "Hotkey: double-tap Right Alt to start/stop.\n"
            "Voice commands: “<prefix> cancel”, “<prefix> "
            "raw/clean/smart/professional/casual/email/chat/code …”.\n"
            "Speech helpers: say “comma / period / question mark / new "
            "paragraph / new line / bullet point / numbered list …” — "
            "applied before the LLM.")
        group.add(info_row)

        self._update_daemon_status()

    # -- daemon management --------------------------------------------------
    def _daemon_pid(self):
        """PID from data/daemon.pid if that process is still our daemon."""
        try:
            pid = int((BASE_DIR / "data" / "daemon.pid").read_text().strip())
        except Exception:
            return None
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().decode(errors="replace")
            cwd = str(Path(f"/proc/{pid}/cwd").resolve())
            if "app.py" in cmd and cwd == str(BASE_DIR):
                return pid
        except Exception:
            pass
        return None

    def _daemon_running(self):
        if self._daemon_pid() is not None:
            return True
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
        subprocess.run(["pkill", "-f", "autotype.*app\\.py"],
                       capture_output=True, timeout=5)
        subprocess.run(["bash", "-c",
                        "for p in $(pgrep -f 'python app\\.py'); do "
                        "if [ \"$(readlink /proc/$p/cwd)\" "
                        "= \"" + str(BASE_DIR) + "\" ]; then kill $p; fi; done"],
                       capture_output=True, timeout=5)

    def _update_daemon_status(self, _row=None):
        running = self._daemon_running()
        self.daemon_row.set_subtitle(
            "Running (double-tap Right Alt to dictate)"
            if running else "Stopped")
        self.daemon_row.set_icon_name(
            "object-select-symbolic" if running
            else "dialog-warning-symbolic")
        try:
            logdir = BASE_DIR / "logs"
            logs = sorted(logdir.glob("*.log"),
                          key=lambda p: p.stat().st_mtime) if logdir.exists() \
                else []
            text = ""
            if logs:
                text = logs[-1].read_text(encoding="utf-8",
                                          errors="replace")[-6000:]
            self.log_view.get_buffer().set_text(text or "(no logs yet)")
        except Exception as exc:
            self.log_view.get_buffer().set_text(f"(log read failed: {exc})")

    def _on_restart_daemon(self, _row=None):
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

    # -- misc ---------------------------------------------------------------
    def _combo_value(self, combo):
        return combo.get_active_text() or ""

    def _refresh_combo(self, combo, names, active):
        combo.remove_all()
        for n in names:
            combo.append_text(n)
        try:
            combo.set_active(names.index(active))
        except ValueError:
            combo.set_active(0)


def main():
    win = SettingsWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
