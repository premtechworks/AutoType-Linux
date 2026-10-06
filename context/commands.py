"""Spoken-prefix voice commands. Unknown input stays normal dictation."""

CANCEL_PHRASES = (
    "cancel", "never mind", "nevermind", "scratch that", "forget it",
)
# One-shot modes: "<prefix> email ..." etc. `smart` = auto from active app.
MODE_WORDS = (
    "raw", "clean", "smart",
    "professional", "casual", "email", "chat", "code",
)


def detect_command(transcript: str, prefix: str) -> dict | None:
    """Return {"action": ...} or None if this is normal dictation.

    Actions: cancel (discard utterance) or mode override
    {"action": "mode", "mode": ..., "text": ...}.
    Matching is strict so ordinary speech is never eaten.
    """
    text = transcript.strip().rstrip(".,!?").strip()
    low = text.lower()
    pre = prefix.strip().lower()
    if not pre or not low.startswith(pre):
        return None
    rest = text[len(pre):].lstrip(" ,.!?-").strip()
    rest_low = rest.lower()
    if rest_low in CANCEL_PHRASES:
        return {"action": "cancel"}
    for mode in MODE_WORDS:
        if rest_low == mode or rest_low.startswith(mode + " "):
            return {
                "action": "mode",
                "mode": mode,
                "text": rest[len(mode):].strip(" ,.!?-"),
            }
    return None
