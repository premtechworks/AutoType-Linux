# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-10

### Added
- Unified `autotype` command-line interface with subcommands: `daemon`, `settings`, `version`, `download-model`, and `doctor`.
- XDG Base Directory specification compliance with unified `config.toml` at `~/.config/autotype/config.toml` and state at `~/.local/share/autotype`.
- Automatic migration from legacy `.env` configurations to `config.toml`.
- Diagnostic command `autotype doctor` (and `autotype doctor --json`) for automated environment, audio, and dependency validation.
- Model manifest and downloader (`autotype download-model`) supporting listing, downloading, checksum verification, and removal of offline GGUF speech models.
- Native GTK3 drop-in preference widgets (`ui/gtk_preferences.py`) providing `ActionRow`, `ExpanderRow`, `PreferencesGroup`, `PreferencesPage`, and `PreferencesWindow`.
- Native X11 keystroke injection and window inspection using `python-xlib` and the XTest extension.
- Native GTK3 clipboard management via `Gtk.Clipboard` for capturing prior state, inserting dictation, and restoring previous text or images.
- Pause-resilient multi-turn speech accumulation across 2+ second pauses in Deepgram Flux streaming.
- Integrated square stop button (`■`) on the glassmorphic floating pill overlay widget for immediate cancellation.
- Packaging specifications and manifests for Debian (`.deb`), Fedora (`.rpm`), AppImage, and Flatpak.
- First-run guidance prompt when no STT credentials or local models are configured.

### Changed
- Refactored `config.py` into a backwards-compatible wrapper re-exporting from `autotype.config`.
- Updated logging handler in `utils/log.py` to support 1 MB rotation, 3 backup files, and automated secret/token redaction.
- Migrated development documentation from `README.md` to `docs/DEVELOPMENT.md`.

### Fixed
- Transcript cutoff issue during speech pauses exceeding 1.5–2 seconds.
- Floating overlay geometry locked to 300x78 to prevent horizontal expansion drift during long utterances.
- Non-linear waveform scaling curve applied for improved visual responsiveness during moderate speech.
- Handling of Deepgram `FORCE_END_TURN_NO_ACTIVE_TURN` warnings to avoid 15-second settling timeouts.

### Removed
- Hard dependency on `gir1.2-handy-1` (`libhandy-1`), allowing execution on vanilla GTK3 without GNOME/Handy packages.
- Hard runtime dependencies on `xclip` and `xdotool` (retained solely as fallback mechanisms).
- Desktop `Escape` key interception listener in favor of the on-widget stop button.

### Security
- Added automated redaction of API keys (OpenAI, Anthropic, Deepgram, Groq, NVIDIA) in daemon logs.
- Enforced strict 0600 permissions on `config.toml` containing stored API secrets.
- Checksum validation for all downloaded speech models and binary assets.

### Known issues
- AutoType requires an X11 display session; Wayland sessions are not supported.
- Bluetooth headset profile auto-switching requires `pactl` from `pulseaudio-utils`.
- Flatpak sandbox requires host X11 socket access; global hotkey double-tap requires X11 input listener permissions.
