"""Actionable error diagnostics and message formatting for AutoType.

Maps low-level exceptions (PortAudio, HTTP 401, ConnectionError, FileNotFoundError)
to user-facing, actionable overlay error strings that guide the user to the
appropriate Settings pane:
- Settings → Speech
- Settings → Cleaning
- Settings → Microphone
"""
from __future__ import annotations


def format_actionable_error(exc: Exception | str, context: str = "") -> str:
    """Format an exception into a specific, actionable message naming the setting to change.

    Parameters
    ----------
    exc : Exception | str
        The exception instance or error string.
    context : str
        Optional context hint: "stt", "llm", "mic", "session".

    Returns
    -------
    str
        Actionable error message.
    """
    msg = str(exc)
    msg_lower = msg.lower()
    ctx_lower = context.lower()

    # 1. Session is not X11
    if any(k in msg_lower for k in ("wayland", "display environment variable", "session is not x11")) or ctx_lower == "session":
        return "Session is not X11 (Select X11 at login screen)"

    # 2. No microphone detected
    if any(k in msg_lower for k in (
        "no microphone detected",
        "no audio capture devices",
        "device unavailable",
        "no default input device",
        "error querying device",
        "could not open microphone",
        "invalid input device",
        "portaudioerror",
        "microphone error",
    )) or (ctx_lower == "mic" and any(k in msg_lower for k in ("device", "channel", "input", "sound", "audio", "mic"))):
        return "No microphone detected (Settings → Microphone)"

    # 3. Local model or binary not found
    if any(k in msg_lower for k in (
        "binary not found",
        "model not found",
        "parakeet-cli not found",
        "parakeet binary",
        "parakeet model",
        "streaming binary",
        "streaming model",
        "missing parakeet",
    )):
        return "Local STT binary or model not found (Settings → Speech)"

    # 4. Missing or invalid STT API key
    if any(k in msg_lower for k in ("deepgram_api_key", "missing deepgram api key")):
        return "Missing Deepgram API key (Settings → Speech)"
    if any(k in msg_lower for k in ("cloud_stt_api_key", "missing api key for cloud stt")):
        return "Missing Cloud STT API key (Settings → Speech)"
    if ctx_lower == "stt" or any(k in msg_lower for k in ("deepgram", "cloud stt", "whisper", "groq", "transcribe")):
        if any(k in msg_lower for k in ("401", "unauthorized", "invalid api key", "authentication", "forbidden", "403")):
            return "Invalid STT API key (Settings → Speech)"
        if any(k in msg_lower for k in ("missing api key", "no api key")):
            return "Missing STT API key (Settings → Speech)"

    # 5. Missing or invalid LLM API key
    if any(k in msg_lower for k in ("missing anthropic api key", "missing llm api key")):
        return "Missing LLM API key (Settings → Cleaning)"
    if ctx_lower == "llm" or "clean" in ctx_lower:
        if any(k in msg_lower for k in ("401", "unauthorized", "invalid api key", "authentication", "forbidden", "403")):
            return "Invalid LLM API key (Settings → Cleaning)"
        if any(k in msg_lower for k in ("missing api key", "no api key")):
            return "Missing LLM API key (Settings → Cleaning)"

    # 6. LLM endpoint unreachable
    if ctx_lower == "llm" or "clean" in ctx_lower or any(k in msg_lower for k in ("connection", "timeout", "unreachable", "refused", "502", "503", "504", "failed to establish")):
        if ctx_lower == "llm" or "clean" in ctx_lower:
            return "LLM endpoint unreachable; pasted raw (Settings → Cleaning)"

    return f"Error: {msg}"
