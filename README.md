# AutoType

Voice typing for Linux Mint XFCE. Double-tap **Right Alt**, speak, and clean formatted text is instantly pasted into whatever window you are using.

AutoType is a fast, flexible, open-source Linux alternative to [Wispr Flow](https://wisprflow.ai). It runs as a lightweight, silent background daemon: listening for a single hotkey gesture, converting speech to text, intelligently cleaning the transcription, and typing it into your active app.

**Bring your own providers**: AutoType is completely provider-agnostic. Choose any popular AI provider for text cleaning (**OpenAI, Anthropic Claude, xAI Grok, DeepSeek, Qwen, NVIDIA NIM, Groq, OpenRouter, Ollama**, or your own **Custom API endpoint** like OmniRoute or vLLM). For voice transcription, choose between **Cloud STT** (Deepgram, OpenAI Whisper, Groq, NVIDIA NIM) or **100% Local Offline STT** (Parakeet streaming and batch models).

---

## What It Does

1. **Trigger anywhere**: Double-tap `Right Alt` in any text field, IDE, browser, or terminal.
2. **Audio feedback**: A subtle floating pill appears above the taskbar displaying a live waveform meter and real-time accumulated transcription.
3. **Speech-to-Text with pause resilience**: Captures your voice via Cloud STT or 100% on-device Local STT. Short or long pauses (2+ seconds) never cut off or discard your dictation; all audio between starting and stopping is transcribed continuously.
4. **Instant cancellation**: Click the integrated square stop button (`■`) on the floating pill overlay at any point during listening, transcribing, or cleaning to abort immediately without pasting, leaving the background daemon ready for your next dictation.
5. **Deterministic normalization**: Handles spoken punctuation (`"comma"`, `"new line"`), bulleted lists, and personal vocabulary casing without hallucinations.
6. **Intelligent LLM cleanup**: Removes stutters and filler words (`"um"`, `"uh"`), formats code snippets, and matches the tone of your current application.
7. **Instant paste**: Automatically pastes the text into the focused window and restores your previous clipboard contents.

The same gesture (double-tapping `Right Alt`) stops recording and triggers typing.

---

## Why Choose AutoType Over Wispr Flow?

Wispr Flow is a proprietary, subscription-based commercial application primarily focused on macOS and Windows. AutoType is purpose-built for Linux users who want complete control over their desktop, privacy, and models.

| Feature | AutoType | Wispr Flow |
| --- | --- | --- |
| **Linux Native** | Built for Linux Mint XFCE & X11 desktops | Not a primary platform |
| **Pricing** | **100% Free & Open Source**. Pay only your own API provider rates (fractions of a cent) or run completely free offline | Monthly/annual paid subscription |
| **Pause Resilience** | **Multi-turn accumulation**: 2+ second pauses never discard or cut off speech | Cuts off or splits utterances on silence |
| **Midway Cancellation** | **On-widget square stop button (`■`)** cancels cleanly at any stage | Limited / hotkey dependent |
| **Offline Speech** | **Yes** — 100% offline Local STT using Parakeet GGUF models | Cloud only |
| **LLM Cleaning Provider** | **Bring your own**: OpenAI, Anthropic, Grok, DeepSeek, Qwen, NVIDIA NIM, Groq, Ollama, or Custom endpoints | Proprietary locked model |
| **Custom Prompts & Vocab** | Full control over system prompts, vocabulary lists, and style modes | Limited custom dictionary |
| **Clipboard Safety** | Automatically backs up and restores previous clipboard contents | Overwrites clipboard |
| **Privacy** | Choose 100% on-device processing (Local STT + Local LLM) with zero data leaving your PC | Audio streamed to third-party cloud |

---

## Architecture: How a Sentence Reaches Your Screen

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
   • Window detection (xdotool) → adaptive style (code / email / chat)
   • Auto-paste into focused window (Ctrl+V / Ctrl+Shift+V)
   • Clipboard restored to previous content
```

---

## 1. LLM Cleaning Providers

AutoType eliminates hardcoded vendor lock-in. You can use any major AI provider or bring your own self-hosted server:

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

Configure your provider easily via the graphical **Settings GUI** or by editing `.env`.

---

## 2. Speech-to-Text: Cloud vs Local

AutoType cleanly separates speech recognition into two distinct pipelines:

### Cloud STT (Online API)

For maximum vocabulary coverage and rapid setup using cloud APIs:

- **Deepgram**: Real-time websocket streaming with Deepgram Flux (`flux-general-en`) and batch accuracy with Nova-3 (`nova-3`).
- **OpenAI Whisper**: Standard cloud transcription (`whisper-1`).
- **Groq Whisper Cloud**: Accelerated Whisper Large v3 Turbo processing in ~250ms.
- **NVIDIA NIM Cloud ASR**: Accelerated cloud speech recognition (`nvidia/parakeet-ctc-1.1b-asr`).
- **Custom Cloud STT**: Connect to any OpenAI-compatible `/v1/audio/transcriptions` endpoint.

### Local STT (100% Offline & Private)

For air-gapped environments or total data sovereignty:

- **Parakeet Stream**: Real-time on-device streaming powered by `parakeet-cli` and an End-of-Utterance (EOU) 120M GGUF model. Audio is transcribed as you speak.
- **Parakeet Batch**: High-accuracy offline transcription powered by `transcribe-cli` and a 0.6B GGUF model. Transcribes immediately upon releasing the hotkey.

---

## Prerequisites

- **Linux Mint XFCE** (or any X11 desktop environment). *Note: Wayland is not supported as window-tracking and synthetic keystrokes rely on X11.*
- **Python 3.10+** (developed on Python 3.12).
- **Audio subsystem**: PipeWire (recommended) or PulseAudio.
- **API Keys**: Depending on your choice of Cloud STT and AI Cleaning Provider.

---

## Installation & Setup

### 1. Install System Dependencies

```bash
sudo apt update
sudo apt install \
  python3 python3-venv python3-pip \
  python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-handy-1 \
  libportaudio2 \
  xclip xdotool libnotify-bin pulseaudio-utils
```

### 2. Clone the Repository & Setup Virtual Environment

```bash
git clone https://github.com/premtechworks/AutoType-Linux.git
cd AutoType-Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Your Environment (`.env`)

```bash
cp .env.example .env
chmod 600 .env
```

Open `.env` in your editor or configure everything via the GTK Settings GUI.

#### Example 1: OpenAI (ChatGPT) + Deepgram Cloud STT

```env
# Cleaning Provider
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Speech Engine
STT_BACKEND=deepgram
DEEPGRAM_API_KEY=your_deepgram_key
```

#### Example 2: Anthropic (Claude) + Groq Whisper STT

```env
# Cleaning Provider
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_MODEL=claude-3-5-haiku-20241022

# Speech Engine
STT_BACKEND=groq
CLOUD_STT_API_KEY=gsk_...
CLOUD_STT_BASE_URL=https://api.groq.com/openai/v1
CLOUD_STT_MODEL=whisper-large-v3-turbo
```

#### Example 3: 100% Local & Offline (Ollama + Parakeet)

```env
# Cleaning Provider
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.2

# Speech Engine (100% Offline)
STT_BACKEND=parakeet_stream
PARAKEET_STREAM_BINARY=/path/to/parakeet-cli
PARAKEET_STREAM_MODEL=/path/to/parakeet-eou-120m-q8_0.gguf
```

#### Example 4: Custom API Provider (e.g. OmniRoute)

```env
# Custom API Endpoint
LLM_PROVIDER=custom
LLM_BASE_URL=http://127.0.0.1:20128/v1
LLM_API_KEY=your_key
LLM_MODEL=auto

STT_BACKEND=deepgram
DEEPGRAM_API_KEY=your_deepgram_key
```

*(Note: Legacy `OMNIROUTE_*` environment variables are automatically mapped to `LLM_*` for backwards compatibility).*

---

## Graphical Settings GUI

AutoType comes with an intuitive, native GTK3/libhandy settings manager:

```bash
./open-settings.sh
```

*(Or right-click the tray icon and select **Settings…**).*

### Settings Pages

- **General**: Choose default processing mode (`clean`, `raw`, `smart`, `code`), configure personal vocabulary, and restart the daemon.
- **Speech**: Switch between **Cloud STT** (Deepgram, OpenAI, Groq, NVIDIA, Custom) and **Local STT** (Parakeet Stream/Batch). Test API credentials and verify local binary files.
- **Cleaning**: Select your **API Provider** (OpenAI, Anthropic Claude, Grok, DeepSeek, Qwen, NVIDIA NIM, Groq, Ollama, Custom). The UI automatically populates the correct base URLs and default models. Run live connection tests on your endpoint.
- **Microphone**: Select your input hardware, follow dynamic PipeWire switches, and toggle Bluetooth HSP/HFP voice profiles.
- **Advanced**: Toggle debug WAV dumps and customize keyboard timings.

---

## How to Use

### Basic Voice Typing

1. Place your cursor in any application (browser, Slack, VS Code, terminal).
2. Double-tap **Right Alt** (two quick taps within 0.4s).
3. The on-screen pill turns red with a live waveform showing active recording.
4. Speak naturally. Take your time to think or breathe — pauses (even 2+ seconds or longer) will not cut off your audio.
5. Double-tap **Right Alt** again.
6. The pill transitions to `Transcribing...` → `Cleaning...` → `Done`, and types the result directly into your active window.

### Continuous Dictation & Natural Pauses

Unlike conventional speech systems that drop or overwrite earlier speech when you pause, AutoType uses **multi-turn turn accumulation**:
- Pausing for 2 or more seconds to think or breathe keeps your entire previous stream intact.
- The floating pill displays your full cumulative dictation as you speak.
- 100% of the speech captured between turning ON listening and turning OFF listening (double-tap `Right Alt`) is passed to cleaning and pasting.

### Instant Cancellation (On-Widget Stop Button)

Need to abort what you just said midway?

- Click the square **Stop** button (`■`) embedded directly on the floating pill overlay at any time while listening, transcribing, or cleaning.
- The active audio capture or background processing terminates immediately, the floating widget disappears, and no text is pasted.
- The button stays visible across listening, transcribing, and cleaning states, disappearing along with the widget once processing completes or is cancelled.
- The daemon remains running silently in the background, ready for your next dictation gesture (double-tap `Right Alt`).

### Floating Taskbar Pill Widget

The floating pill widget sits unobtrusively centered above your taskbar on X11:

- **Zero Focus Stealing**: Built as a native GTK3 popup with `accept_focus=False`, ensuring your keyboard focus never leaves your active window, IDE, or terminal.
- **Embedded Stop Button (`■`)**: A discreet square stop button styled seamlessly within the header bar. Clicking it terminates all in-flight audio capture, STT transcription, and LLM cleaning without stealing focus or altering clipboard history.
- **Dynamic Waveform States**:
  - 🔴 **Listening (Red)**: Displays a 30-bar live audio amplitude meter alongside your real-time cumulative transcription.
  - 🔵 **Processing (Blue)**: Animated traveling sine wave pulse during `Transcribing...` and `Cleaning...`.
  - 🟠 **Error (Orange)**: Shows actionable error messages and automatically dismisses after 2.5 seconds.
- **Smart Text Ellipsization**: Long live utterances are smoothly ellipsized (`...`) with Pango, guaranteeing the square stop button remains cleanly aligned and never clipped off-screen.

### Voice Commands

Start your dictation with your configured `COMMAND_PREFIX` (default: `"computer"`) to trigger instant actions:

| Voice Command | Action |
| --- | --- |
| `computer cancel` | Discards the current recording (also accepts `"never mind"`, `"scratch that"`) |
| `computer raw ...` | One-shot raw paste (bypasses LLM rewriting) |
| `computer clean ...` | Standard AI cleanup |
| `computer smart ...` | Automatically matches the style of the focused application |
| `computer professional ...` | Strict business/formal tone |
| `computer casual ...` | Friendly, informal messaging tone |
| `computer email ...` | Structured email layout |
| `computer code ...` | Preserves camelCase, snake_case, paths, and syntax literally |

### Spoken Punctuation & Lists

Normalizer runs deterministically on your device:

- **Punctuation**: `"comma"`, `"period"`, `"question mark"`, `"exclamation mark"`, `"colon"`, `"semicolon"`, `"dash"`, `"open quote" / "close quote"`, `"new line"`, `"new paragraph"`.
- **Lists**: Say `"bullet point"` or `"numbered list ... first ... second ..."` to generate formatted lists.

---

## Running in the Background

### Run Directly

```bash
source .venv/bin/activate
python app.py
```

### Run Detached in Background

```bash
nohup .venv/bin/python app.py >/dev/null 2>&1 &
```

### Auto-start at Login (Linux Mint XFCE)

1. Open **Settings → Session and Startup → Application Autostart**.
2. Click **Add**.
3. Set **Command** to:

   ```bash
   /full/path/to/AutoType-Linux/.venv/bin/python /full/path/to/AutoType-Linux/app.py
   ```

---

## Audio Hardware & Hardware Insights

- **ALSA `default` Capture vs PipeWire**: On many Linux Mint installations, targeting ALSA's default device results in zero audio capture (digital silence). AutoType explicitly uses PipeWire ALSA routing when `MIC_DEVICE` is left empty, ensuring seamless dynamic switching between internal microphones and external headsets.
- **Bluetooth Headset Profiles**: Bluetooth A2DP is a high-fidelity playback-only profile with no microphone channel. AutoType includes automatic profile switching to HSP/HFP (mSBC wideband with fallback to CVSD narrowband), ensuring headsets work smoothly.
- **Fallback Reliability**: If your LLM provider endpoint is unreachable or times out, AutoType gracefully falls back to the normalized transcript rather than discarding your dictation.

---

## Codebase Structure

```text
AutoType/
├── app.py                 # Daemon lifecycle, double-tap hotkey listener, pipeline orchestrator
├── config.py              # Central configuration loader (.env parser with fallback logic)
├── settings_gui.py        # Native GTK3/libhandy graphical configuration app
├── open-settings.sh       # Convenience launcher for Settings GUI
│
├── audio/                 # Microphone stream capture, level metering, Bluetooth routing
├── stt/                   # Speech-to-Text backends
│   ├── deepgram.py        # Cloud STT: Deepgram Nova-3 batch
│   ├── flux.py            # Cloud STT: Deepgram Flux real-time streaming
│   ├── cloud_whisper.py   # Cloud STT: OpenAI Whisper / Groq / NVIDIA NIM / Custom endpoints
│   ├── parakeet.py        # Local STT: Offline batch (transcribe-cli 0.6B)
│   ├── parakeet_stream.py # Local STT: Offline real-time streaming (parakeet-cli 120M)
│   └── factory.py         # Dynamic STT transcriber dispatch
│
├── llm/                   # Provider-Agnostic LLM Cleaning
│   ├── processor.py       # Multi-provider client (OpenAI, Anthropic, Grok, DeepSeek, Qwen, etc.)
│   ├── prompts.py         # Style definitions (smart/clean/code/email/casual) and system prompts
│   ├── normalizer.py      # Deterministic text normalizer (punctuation, lists, spacing)
│   ├── vocabulary.py      # Personal vocabulary capitalization matcher
│   └── omniroute.py       # Backwards-compatible alias for LLMProcessor
│
├── context/               # Window detection, voice commands, clipboard history
├── desktop/               # X11 clipboard integration, key simulation, window title parsing
├── ui/                    # Floating taskbar overlay pill with stop button, tray icon, profile storage
└── data/                  # Local history logs, custom prompt, personal vocabulary
```

---

## Privacy & Security

- **Secrets Stay Local**: `.env` and `data/gui_settings.json` store your keys locally with restricted permissions (`chmod 600`) and are strictly ignored by git.
- **100% Offline Mode**: Pairing Local STT (`parakeet_stream` or `parakeet`) with Local LLM Cleaning (`ollama`) guarantees zero audio or text data ever leaves your computer.
- **Clipboard Restoration**: AutoType preserves and restores your previous clipboard contents after every dictation paste.

---

## License

This project is licensed under the [MIT License](LICENSE).
