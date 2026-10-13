# AutoType Configuration Reference

AutoType uses a unified configuration file, `config.toml`, stored according to the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html).

- **Location**: `$XDG_CONFIG_HOME/autotype/config.toml` (defaults to `~/.config/autotype/config.toml`)
- **Permissions**: `0600` (`chmod 600`), readable and writable only by the current user, because it may store API keys.

---

## Configuration Precedence

AutoType resolves settings using a strict 3-tier hierarchy:

1. **Environment Variables**: Any active environment variable (including variables defined in a `.env` file) takes highest precedence.
2. **Configuration File (`config.toml`)**: Values specified in `$XDG_CONFIG_HOME/autotype/config.toml`.
3. **Built-in Defaults**: Fallback defaults if neither an environment variable nor a TOML key is defined.

This ensures advanced workflows, automated scripts, and legacy `.env` configurations continue to work seamlessly.

---

## Automatic First-Run Migration

On first launch, if `config.toml` does not yet exist:
- AutoType checks for legacy configuration sources: `.env` and `data/gui_settings.json` (or `$XDG_DATA_HOME/autotype/gui_settings.json`).
- If either is found, settings and saved GUI profiles are imported into `config.toml`.
- The new `config.toml` is written with `0600` permissions.
- The original `.env` and `gui_settings.json` files are **left intact and unmodified**.
- Migrated settings are logged. Sensitive keys (API keys, tokens, secrets) are **always masked and never printed to logs**.

---

## 1:1 Setting Mapping

Every setting maps 1:1 between its environment variable representation and its `config.toml` table/key.

### `[general]` — General Daemon & Audio Settings

| `config.toml` Key | Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `processing_mode` | `PROCESSING_MODE` | string | `"clean"` | Text processing mode: `"raw"`, `"clean"`, `"smart"`, `"professional"`, `"casual"`, `"email"`, `"chat"`, or `"code"`. |
| `command_prefix` | `COMMAND_PREFIX` | string | `"computer"` | Trigger keyword for voice command detection. |
| `save_recordings` | `SAVE_RECORDINGS` | boolean | `false` | When `true`, saves audio WAV files to the recordings directory for inspection. |
| `use_custom_prompt` | `USE_CUSTOM_PROMPT` | boolean | `false` | When `true`, overrides built-in system prompt with user custom prompt. |
| `custom_prompt_file` | `CUSTOM_PROMPT_FILE` | string | `""` | Optional explicit path to custom prompt file (defaults to `custom_prompt.txt` in data dir). |
| `mic_device` | `MIC_DEVICE` | string | `""` | Preferred microphone device name (empty string follows system default / PipeWire). |

### `[llm]` — LLM Post-Processing & Text Cleaning

| `config.toml` Key | Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `provider` | `LLM_PROVIDER` | string | `"openai"` | LLM provider: `"openai"`, `"anthropic"`, `"xai"`, `"deepseek"`, `"qwen"`, `"nvidia"`, `"groq"`, `"openrouter"`, `"ollama"`, or `"custom"`. |
| `base_url` | `LLM_BASE_URL` | string | *Provider default* | Base URL for LLM API (e.g., `https://api.openai.com/v1` or `http://localhost:11434/v1`). |
| `api_key` | `LLM_API_KEY` | string | `""` | API key for the chosen LLM provider. |
| `model` | `LLM_MODEL` | string | *Provider default* | Model name (e.g., `"gpt-4o-mini"`, `"claude-3-5-haiku-20241022"`, `"llama3.2"`). |
| `temperature` | `CLEANING_TEMPERATURE` | float | `0.1` | Sampling temperature for the cleanup model (lower is more deterministic). |
| `omniroute_base_url` | `OMNIROUTE_BASE_URL` | string | `""` | Legacy alias for `base_url`. |
| `omniroute_api_key` | `OMNIROUTE_API_KEY` | string | `""` | Legacy alias for `api_key`. |
| `omniroute_model` | `OMNIROUTE_MODEL` | string | `""` | Legacy alias for `model`. |

### `[stt]` — Speech-to-Text Engines

| `config.toml` Key | Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `backend` | `STT_BACKEND` | string | `"deepgram"` | Active STT engine: `"deepgram"`, `"whisper"`, `"openai"`, `"groq"`, `"nvidia"`, `"custom_cloud"`, `"parakeet"`, or `"parakeet_stream"`. |
| `cloud_provider` | `CLOUD_STT_PROVIDER` | string | `"deepgram"` | Provider for generic cloud STT endpoints: `"deepgram"`, `"whisper"`, `"openai"`, `"groq"`, `"nvidia"`, or `"custom"`. |
| `cloud_api_key` | `CLOUD_STT_API_KEY` | string | `""` | API key for cloud STT endpoints. |
| `cloud_base_url` | `CLOUD_STT_BASE_URL` | string | `"https://api.openai.com/v1"` | Base endpoint URL for cloud STT requests. |
| `cloud_model` | `CLOUD_STT_MODEL` | string | `"whisper-1"` | Model identifier for cloud STT requests. |
| `cloud_language` | `CLOUD_STT_LANGUAGE` | string | `"en"` | BCP-47 language tag for cloud STT requests. |
| `deepgram_api_key` | `DEEPGRAM_API_KEY` | string | `""` | Deepgram API key (fallback: `CLOUD_STT_API_KEY`). |
| `deepgram_model` | `DEEPGRAM_MODEL` | string | `"nova-3"` | Deepgram batch transcription model. |
| `deepgram_language` | `DEEPGRAM_LANGUAGE` | string | `"en-US"` | Deepgram transcription language. |
| `deepgram_flux_model` | `DEEPGRAM_FLUX_MODEL`| string | `"flux-general-en"` | Deepgram Flux live streaming model. |
| `parakeet_binary` | `PARAKEET_BINARY` | string | *Local path* | Path to `transcribe-cli` executable for batch Parakeet STT. |
| `parakeet_model` | `PARAKEET_MODEL` | string | *Local path* | Path to GGUF model for batch Parakeet STT. |
| `parakeet_stream_binary` | `PARAKEET_STREAM_BINARY` | string | *Local path* | Path to `parakeet-cli` executable for streaming Parakeet STT. |
| `parakeet_stream_model` | `PARAKEET_STREAM_MODEL` | string | *Local path* | Path to GGUF model for streaming Parakeet STT. |

### `[profiles]` — Settings GUI Profile Selection & Named Presets

| `config.toml` Key | Type | Description |
| :--- | :--- | :--- |
| `active_stt` | string | Name of currently active STT profile. |
| `active_clean` | string | Name of currently active LLM cleanup profile. |

Under `[profiles.stt.<name>]` and `[profiles.clean.<name>]`, custom profiles created in the Settings GUI are stored as TOML sub-tables.

---

## Example `config.toml`

```toml
[general]
processing_mode = "clean"
command_prefix = "computer"
save_recordings = false
use_custom_prompt = false
mic_device = ""

[llm]
provider = "openai"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."
model = "gpt-4o-mini"
temperature = 0.1

[stt]
backend = "deepgram"
deepgram_api_key = "your-deepgram-key"
deepgram_model = "nova-3"
deepgram_language = "en-US"
deepgram_flux_model = "flux-general-en"

[profiles]
active_stt = "Deepgram (Fast)"
active_clean = "OpenAI Mini"

[profiles.stt."Deepgram (Fast)"]
STT_BACKEND = "deepgram"
DEEPGRAM_MODEL = "nova-3"
DEEPGRAM_LANGUAGE = "en-US"

[profiles.clean."OpenAI Mini"]
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4o-mini"
CLEANING_TEMPERATURE = "0.1"
```

---

## XDG Paths & Development Mode

AutoType stores application files according to XDG standards:

1. **Configuration Directory**: `$XDG_CONFIG_HOME/autotype` (default: `~/.config/autotype`)
   - `config.toml`: Unified configuration file.
2. **User Data Directory**: `$XDG_DATA_HOME/autotype` (default: `~/.local/share/autotype`)
   - `history.jsonl`: Transcription and cleanup event history.
   - `vocabulary.json`: Custom casing and dictionary overrides.
   - `custom_prompt.txt`: User-supplied system prompt.
   - `profiles.json`: App profile hints and window class overrides.
   - `bt_audio.json`: Bluetooth SCO/A2DP audio profile states.
   - `daemon.pid`: PID file tracking running background daemon.

### Git Checkout Development Fallback
When AutoType is executed from a git development checkout (where `.git` is present in the repository root) and the local `data/` directory exists, AutoType automatically uses the project-relative `data/` directory instead of `$XDG_DATA_HOME/autotype`. This keeps repository development self-contained without polluting the user's system data directory. The chosen mode is reported in the startup logs:
- `Using project-relative data directory: ... (git checkout mode)`
- `Using XDG data directory: ... (XDG mode)`
