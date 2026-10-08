"""Deepgram Flux streaming STT (cloud, low-latency).

Verified against current docs + deepgram-sdk v7:
- client.listen.v2.connect(model="flux-general-en", encoding="linear16",
  sample_rate=16000), sync connection object
- connection.on(EventType.MESSAGE, handler) + start_listening() in a thread
- connection.send_media(bytes): ~80 ms chunks (2560 bytes @16kHz linear16)
- connection.send_force_end_turn(): ends turn on push-to-talk release,
  EndOfTurn arrives with trigger="manual"
- TurnInfo events carry `transcript` (Update/EagerEndOfTurn = partials,
  EndOfTurn = final)
"""
import threading
import time

from deepgram import DeepgramClient
from deepgram.core.events import EventType

from .base import Transcriber  # noqa: F401  (interface compatibility note)


class FluxStreamer:
    """One utterance = one instance. Not reusable across turns."""

    def __init__(self, api_key: str, model: str = "flux-general-en"):
        if not api_key:
            raise RuntimeError("Missing DEEPGRAM_API_KEY in .env.")
        self.api_key = api_key
        self.model = model
        self._cm = None
        self._conn = None
        self._final_settled = threading.Event()
        self._turns: list[str] = []
        self._current_partial = ""
        self._turn_in_progress = False
        self._lock = threading.Lock()
        self._error: Exception | None = None
        self._chunks_sent = 0
        self.on_partial = None  # called with partial text (SDK thread)

    # -- message handling (runs on the SDK listener thread) -------------
    def _handle_message(self, message) -> None:
        try:
            mtype = getattr(message, "type", None)
            if mtype == "Warning":
                code = getattr(message, "code", "")
                print(f"Flux warning: {code}: {message}", flush=True)
                if code == "FORCE_END_TURN_NO_ACTIVE_TURN":
                    with self._lock:
                        self._turn_in_progress = False
                    self._final_settled.set()
                return
            if mtype != "TurnInfo":
                # Warnings/connection notes — log, they explain missing finals.
                print(f"Flux non-turn message: {mtype}: {message}", flush=True)
                return
            event = getattr(message, "event", None)
            text = (getattr(message, "transcript", "") or "").strip()
            if event == "EndOfTurn":
                trigger = getattr(message, "trigger", "?")
                print(f"Flux EndOfTurn (trigger={trigger}): {text!r}", flush=True)
                with self._lock:
                    if text:
                        self._turns.append(text)
                    self._current_partial = ""
                    self._turn_in_progress = False
                    cumulative = " ".join(self._turns).strip()
                if self.on_partial and cumulative:
                    try:
                        self.on_partial(cumulative)
                    except Exception:
                        pass
                self._final_settled.set()
            elif event in ("Update", "EagerEndOfTurn", "StartOfTurn", "TurnResumed"):
                if event != "Update":
                    print(f"Flux event: {event}", flush=True)
                with self._lock:
                    self._turn_in_progress = True
                    if text:
                        self._current_partial = text
                    parts = [*self._turns]
                    if self._current_partial:
                        parts.append(self._current_partial)
                    cumulative = " ".join(parts).strip()
                if text and self.on_partial and cumulative:
                    try:
                        self.on_partial(cumulative)
                    except Exception:
                        pass
        except Exception as exc:
            self._error = exc
            self._final_settled.set()

    def _handle_error(self, error) -> None:
        self._error = error if isinstance(error, Exception) else RuntimeError(str(error))
        self._final_settled.set()

    # -- lifecycle --------------------------------------------------------
    def start(self, on_partial=None) -> None:
        self.on_partial = on_partial
        client = DeepgramClient(api_key=self.api_key)
        self._cm = client.listen.v2.connect(
            model=self.model, encoding="linear16", sample_rate=16000,
            eot_timeout_ms=3000,
        )
        self._conn = self._cm.__enter__()
        self._conn.on(EventType.MESSAGE, self._handle_message)
        self._conn.on(EventType.ERROR, self._handle_error)
        threading.Thread(target=self._conn.start_listening, daemon=True).start()

    def send_audio(self, chunk: bytes) -> None:
        if self._conn is not None and chunk:
            self._conn.send_media(chunk)
            self._chunks_sent += 1

    def finish(self, timeout: float = 15.0) -> str:
        """Force end of turn (push-to-talk release) and wait for the final transcript."""
        if self._conn is None:
            raise RuntimeError("Flux stream was never started.")
        print(f"Flux: {self._chunks_sent} chunks sent, forcing end of turn...",
              flush=True)
        try:
            # Grace period: let the last in-flight audio reach the server.
            time.sleep(0.3)
            self._final_settled.clear()
            try:
                self._conn.send_force_end_turn()
            except Exception:
                pass  # no active turn -> server answers Warning; EndOfTurn may never come
            settled = self._final_settled.wait(timeout=timeout)
        finally:
            try:
                self._cm.__exit__(None, None, None)
            except Exception:
                pass
            self._conn = None
        if self._error is not None:
            raise RuntimeError(f"Flux stream failed: {self._error}")

        with self._lock:
            if self._current_partial and (not self._turns or self._current_partial != self._turns[-1]):
                self._turns.append(self._current_partial)
            full_transcript = " ".join(self._turns).strip()

        if not settled and not full_transcript:
            raise RuntimeError("Timed out waiting for Flux final transcript.")
        return full_transcript

    def abort(self) -> None:
        try:
            if self._cm is not None:
                self._cm.__exit__(None, None, None)
        except Exception:
            pass
        finally:
            self._conn = None
            self._final_settled.set()
