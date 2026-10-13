# AutoType

AutoType is a fast, flexible, open-source Linux voice-typing assistant and background daemon built for Linux Mint XFCE and X11 desktop environments. Double-tap **Right Alt**, speak, and clean, formatted text is instantly typed into your active window.

---

## Features

- **Voice Dictation Anywhere**: Double-tap `Right Alt` in any text field, code editor, browser, or terminal to begin and end dictation.
- **Cloud STT**: Low-latency transcription via Deepgram (Flux real-time & Nova-3), OpenAI Whisper, Groq Whisper (<300ms), NVIDIA NIM, or custom OpenAI-compatible speech endpoints.
- **100% Offline STT**: Air-gapped, on-device transcription with Parakeet GGUF models (`parakeet-cli` streaming and `transcribe-cli` batch).
- **LLM Cleanup Providers**: Intelligent rewriting and filler removal with OpenAI, Anthropic Claude, xAI Grok, DeepSeek, Qwen, NVIDIA NIM, Groq, Ollama (local), or custom endpoints.
- **Voice Commands**: Prefix dictation with `"computer"` for one-shot controls (`computer raw`, `computer code`, `computer email`, `computer cancel`).
- **Deterministic Spoken Punctuation & Lists**: Real-time normalization for punctuation (`"comma"`, `"period"`, `"new line"`) and bulleted/numbered lists without hallucination.
- **Clipboard Restoration**: Captures prior clipboard state and restores text or images immediately after pasting.
- **Floating Glassmorphic Overlay**: Dark translucent widget with vector microphone indicator, 42-bar glowing waveform visualizer, live transcript strip, and an integrated **square stop button (`■`)** for instant cancellation midway.
- **X11 Display Server**: Native keystroke injection via `python-xlib` and GTK3 clipboard integration (X11 only).

---

## Download & Installation

AutoType v1.0.0 release packages can be downloaded from the [GitHub Releases](https://github.com/premtechworks/AutoType-Linux/releases) page.

### 1. Debian / Ubuntu / Linux Mint (`.deb`)

```bash
sudo apt install ./autotype_1.0.0_amd64.deb
```

*Terminal alternative (dpkg):*

```bash
sudo dpkg -i autotype_1.0.0_amd64.deb && sudo apt-get install -f
```

### 2. Fedora / RHEL (`.rpm`)

```bash
sudo dnf install ./autotype-1.0.0-1.x86_64.rpm
```

*Terminal alternative (rpm):*

```bash
sudo rpm -ivh autotype-1.0.0-1.x86_64.rpm
```

### 3. AppImage

```bash
chmod +x AutoType-1.0.0-x86_64.AppImage
./AutoType-1.0.0-x86_64.AppImage
```

### 4. Flatpak

```bash
flatpak install --user ./AutoType-1.0.0.flatpak
flatpak run io.github.premtechworks.AutoType
```

### Verify Integrity

Verify release asset integrity using the provided `SHA256SUMS`:

```bash
sha256sum -c SHA256SUMS
```

---

## First Run & Setup

1. **Configuration File**:
   AutoType adheres to the XDG Base Directory specification. Configuration is stored at:
   ```text
   ~/.config/autotype/config.toml
   ```
   Permissions are strictly locked to `0600` to safeguard stored API credentials.

2. **Open the Settings GUI**:
   Open the native GTK3 preferences manager to configure your providers, hotkeys, and microphones:
   ```bash
   autotype settings
   ```
   *(Or launch "AutoType" from your desktop applications menu).*

3. **Install a Local Speech Model (Optional)**:
   List and install recommended offline GGUF speech models:
   ```bash
   autotype download-model --list
   autotype download-model --all-recommended
   ```

4. **Add an API Key**:
   Configure cloud STT or LLM cleaning API keys either via `autotype settings` or by setting them in `~/.config/autotype/config.toml` (or legacy `.env`):
   ```toml
   [stt]
   backend = "deepgram"
   api_key = "your_deepgram_api_key"

   [llm]
   provider = "openai"
   api_key = "your_openai_api_key"
   model = "gpt-4o-mini"
   ```

5. **Run Diagnostics**:
   Verify that your microphone, audio subsystem, X11 session, and dependencies are functioning correctly:
   ```bash
   autotype doctor
   ```
   For machine-readable JSON output:
   ```bash
   autotype doctor --json
   ```

6. **Start the Background Daemon**:
   ```bash
   autotype daemon
   ```

---

## Upgrading & Uninstalling

### Debian / Ubuntu / Linux Mint
- **Upgrade**: `sudo apt install --only-upgrade ./autotype_1.0.0_amd64.deb`
- **Uninstall**: `sudo apt remove autotype`

### Fedora
- **Upgrade**: `sudo dnf upgrade ./autotype-1.0.0-1.x86_64.rpm`
- **Uninstall**: `sudo dnf remove autotype`

### AppImage
- **Upgrade**: Replace the `.AppImage` binary with the new version and make it executable.
- **Uninstall**: Delete the `.AppImage` file and desktop integration links.

### Flatpak
- **Upgrade**: `flatpak update io.github.premtechworks.AutoType`
- **Uninstall**: `flatpak uninstall --user io.github.premtechworks.AutoType`

---

## Troubleshooting

- **Wayland Not Supported**: AutoType relies on X11 protocol calls (`python-xlib` and XTest extension) for active window introspection and global synthetic keystrokes. Under Wayland, the daemon will refuse to start. Select an **X11 / Xorg** session at your display manager login screen.
- **Flatpak Sandbox Limitations**: The Flatpak bundle requires access to the host X11 socket (`--socket=x11`) and PulseAudio (`--socket=pulseaudio`). Global hotkey listening and window-level auto-pasting may require additional host desktop portal permissions depending on your compositor.
- **Locating Logs**:
  Logs are rotated automatically (1 MB limit, 3 backups) and stored at:
  ```text
  ~/.local/state/autotype/autotype.log
  ```
  Sensitive API keys and bearer tokens are automatically redacted in log files.
- **Filing a Bug Report**:
  When submitting an issue, run and attach the diagnostic report:
  ```bash
  autotype doctor --json > doctor-report.json
  ```

---

## Known Limitations

- **X11 Only**: Linux Mint XFCE, Cinnamon (X11), MATE, and standard X11 sessions are supported. Wayland is not supported.
- **Microphone & Bluetooth**: Bluetooth headsets in A2DP playback mode have no input voice channel. Automatic profile switching to HSP/HFP requires `pactl` from `pulseaudio-utils`.
- **Headless Environments**: GUI overlays, tray icons, global hotkeys, and synthetic keystroke paste operations require an active X11 graphical display (`DISPLAY`).

---

## Development Setup

For instructions on building from source, running tests, and setting up an editable virtual environment, see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## Architecture: How Speech Reaches Your Screen

```text
                    [ Microphone ]
                          │
                          ▼
            [ Speech-to-Text Layer ]
       ┌──────────────────┴──────────────────┐
       ▼                                     ▼
   Cloud STT                             Local STT
 • Deepgram Flux (Multi-Turn Accumulation) • Parakeet Stream (120M EOU)
 • Deepgram Nova-3 Batch              • Parakeet Batch (0.6B GGUF)
 • OpenAI Whisper                     • Zero internet required
 • Groq Whisper (<300ms)
 • NVIDIA NIM Cloud ASR
 • Custom OpenAI-compatible ASR
       └──────────────────┬──────────────────┘
                          │ (Cumulative Transcript)
                          ▼
             [ Deterministic Normalizer ]
   • Spoken punctuation ("period", "question mark", "open quote")
   • Formatting ("new line", "bullet point", "numbered list")
   • Vocabulary casing ("Power BI", "FastAPI", "DataFrame")
                          │
                          ▼
             [ LLM Text Cleaning Layer ]
   • OpenAI (ChatGPT)                 • NVIDIA NIM
   • Anthropic (Claude)               • Groq (Llama-3.3)
   • xAI (Grok)                       • OpenRouter
   • DeepSeek                         • Ollama (Local)
   • Qwen (Alibaba DashScope)         • Custom API (OmniRoute, vLLM)
       (Skipped entirely when using Voice Command or Mode: "raw")
                          │
                          ▼
               [ Desktop Output Layer ]
   • Window detection (python-xlib, xdotool fallback) → adaptive style (code / email / chat)
   • Auto-paste into focused window (Ctrl+V / Ctrl+Shift+V)
   • Clipboard restored to previous content (Gtk.Clipboard)
```

---

## LLM Cleaning Providers

AutoType eliminates vendor lock-in. You can use any major AI provider or bring your own self-hosted endpoint:

| Provider | Protocol | Default Model | Typical Use Case |
| --- | --- | --- | --- |
| **OpenAI (ChatGPT)** | `/v1/chat/completions` | `gpt-4o-mini` | Reliable, fast, high-quality standard |
| **Anthropic (Claude)** | `/v1/messages` (Native) | `claude-3-5-haiku-20241022` | Exceptional instruction following & nuance |
| **xAI (Grok)** | `/v1/chat/completions` | `grok-2-mini` | High-speed processing with modern reasoning |
| **DeepSeek** | `/v1/chat/completions` | `deepseek-chat` | State-of-the-art cost efficiency |
| **Qwen (Alibaba Cloud)** | `/v1/chat/completions` | `qwen-plus` | Strong multilingual and reasoning capability |
| **NVIDIA NIM** | `/v1/chat/completions` | `meta/llama-3.3-70b-instruct` | Enterprise-grade accelerated inference |
| **Groq** | `/v1/chat/completions` | `llama-3.3-70b-versatile` | Ultra-low latency (~200ms turnaround) |
| **OpenRouter** | `/v1/chat/completions` | `meta-llama/llama-3.3-70b-instruct` | Unified gateway to hundreds of open/closed models |
| **Ollama (Local)** | `/v1/chat/completions` | `llama3.2` | 100% private, on-device local cleaning |
| **Custom API Provider** | `/v1/chat/completions` | Custom / `auto` | Bring your own endpoint (e.g. OmniRoute, vLLM, LiteLLM) |

---

## Graphical Settings GUI

AutoType comes with an intuitive, native GTK3 settings manager:

```bash
autotype settings
```

*(Or right-click the system tray icon and select **Settings…**).*

- **General**: Default processing mode (`clean`, `raw`, `smart`, `code`), vocabulary editor, daemon control.
- **Speech**: Switch between Cloud STT and Local STT, test credentials, and download speech models.
- **Cleaning**: Select provider, endpoint URL, and model. Run live connection tests.
- **Microphone**: Select hardware device, follow PipeWire dynamic routing, toggle Bluetooth voice profile.
- **Advanced**: Audio dump toggles, key repeat delays, and timing settings.

---

## Dictation & Voice Assistant Usage

### Continuous Dictation Across Pauses
AutoType features **multi-turn accumulation**:
- Speaking, pausing for 2+ seconds to think, and continuing to speak does not truncate or split your transcription.
- 100% of speech between starting and stopping is accumulated and cleaned.

### Midway Cancellation (Stop Button `■`)
- Clicking the square stop button (`■`) on the floating pill widget immediately aborts listening, transcribing, or cleaning without pasting any text.

### Voice Commands
Start your dictation with your configured `COMMAND_PREFIX` (default: `"computer"`):
- `computer raw ...`: Pastes raw transcript directly without LLM cleaning.
- `computer clean ...`: Standard AI cleanup.
- `computer smart ...`: Adapts tone and structure to the focused window (code, email, chat).
- `computer cancel`: Aborts the recording.

---

## Privacy & Security

- **Local Secrets**: Stored at `~/.config/autotype/config.toml` with `0600` permissions.
- **100% Offline Mode**: Pairing Local STT (`parakeet_stream`) with Local LLM (`ollama`) keeps 100% of speech and text on-device.
- **Clipboard Preservation**: Original clipboard text and images are automatically restored after every paste.

---

## License

This project is licensed under the [MIT License](LICENSE).
