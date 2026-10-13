# AutoType Development Guide

This guide covers setting up a local development environment, running tests, and debugging the AutoType daemon and GTK3 settings interface.

---

## 1. Prerequisites

AutoType runs on Linux under the X11 display server. You will need:
- **Python**: 3.10 or newer (tested on Python 3.10, 3.11, 3.12)
- **GTK3 & PyGObject**: `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`
- **PortAudio**: `libportaudio2`

### Debian / Ubuntu / Linux Mint
```bash
sudo apt update
sudo apt install \
  python3 python3-venv python3-pip \
  python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
  libportaudio2 \
  xdotool libnotify-bin pulseaudio-utils
```

### Fedora
```bash
sudo dnf install \
  python3 python3-pip \
  python3-gobject gtk3 \
  portaudio \
  xdotool libnotify pulseaudio-utils
```

---

## 2. Clone & Virtual Environment Setup

Because AutoType integrates with host GObject introspection bindings, create your virtual environment with `--system-site-packages`:

```bash
git clone https://github.com/premtechworks/AutoType-Linux.git
cd AutoType-Linux

# Create virtual environment inheriting system PyGObject bindings
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# Install development dependencies and editable package
pip install -e ".[dev]" || pip install -e .
pip install pytest build
```

---

## 3. Running Diagnostics

Validate that your environment meets all requirements using the built-in diagnostic CLI:

```bash
autotype doctor
```

For machine-readable JSON output:

```bash
autotype doctor --json
```

---

## 4. Running the Daemon & Settings GUI

### Background Daemon
```bash
# Standard mode
autotype daemon

# Debug logging mode (prints detailed events to stderr and log file)
autotype daemon --debug
```

### Settings Preferences Window
```bash
autotype settings
```

---

## 5. Running the Test Suite

Run unit and integration tests using pytest:

```bash
pytest
```

To run with verbose output:

```bash
pytest -v
```

---

## 6. Architecture Overview

- **`autotype/`**: Core CLI dispatch, unified configuration (`config.toml`), XDG paths, doctor diagnostics, model downloader, and error formatting.
- **`audio/`**: PortAudio/sounddevice capture and Bluetooth audio profile management.
- **`desktop/`**: X11 window introspection via `python-xlib`, clipboard restoration via `Gtk.Clipboard`, and notifications.
- **`stt/`**: Speech-to-text backends (Deepgram Flux streaming, OpenAI Whisper, local Parakeet GGUF).
- **`llm/`**: Post-processing, normalization, and LLM text cleaning.
- **`ui/`**: Glassmorphic floating pill overlay (`overlay.py`), system tray (`tray.py`), native GTK3 preferences (`gtk_preferences.py`).
