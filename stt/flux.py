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
        self._final = threading.Event()
        self._transcript = ""
        self._last_partial = ""
        self._error: Exception | None = None
        self._chunks_sent = 0
        self.on_partial = None  # called with partial text (SDK thread)

    # -- message handling (runs on the SDK listener thread) -------------
    def _handle_message(self, message) -> None:
        try:
            mtype = getattr(message, "type", None)
            if mtype != "TurnInfo":
                # Warnings/connection notes — log, they explain missing finals.
                print(f"Flux non-turn message: {mtype}: {message}", flush=True)
                return
            event = getattr(message, "event", None)
            text = (getattr(message, "transcript", "") or "").strip()
            if event == "EndOfTurn":
                trigger = getattr(message, "trigger", "?")
                print(f"Flux EndOfTurn (trigger={trigger}): {text!r}", flush=True)
                self._transcript = text
                self._final.set()
            elif event in ("Update", "EagerEndOfTurn", "StartOfTurn", "TurnResumed"):
                if event != "Update":
                    print(f"Flux event: {event}", flush=True)
                if text:
                    self._last_partial = text
                    if self.on_partial:
                        try:
                            self.on_partial(text)
                        except Exception:
                            pass
        except Exception as exc:
            self._error = exc
            self._final.set()

    def _handle_error(self, error) -> None:
        self._error = error if isinstance(error, Exception) else RuntimeError(str(error))
        self._final.set()

    # -- lifecycle --------------------------------------------------------
    def start(self, on_partial=None) -> None:
        self.on_partial = on_partial
        client = DeepgramClient(api_key=self.api_key)
        self._cm = client.listen.v2.connect(
            model=self.model, encoding="linear16", sample_rate=16000,
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
        """Force end of turn (push-to-talk release) and wait for the final."""
        if self._conn is None:
            raise RuntimeError("Flux stream was never started.")
        print(f"Flux: {self._chunks_sent} chunks sent, forcing end of turn...",
              flush=True)
        try:
            # Grace period: let the last in-flight audio reach the server.
            time.sleep(0.4)
            try:
                self._conn.send_force_end_turn()
            except Exception:
                pass  # no active turn -> server answers Warning; EndOfTurn may never come
            settled = self._final.wait(timeout=timeout)
        finally:
            try:
                self._cm.__exit__(None, None, None)
            except Exception:
                pass
            self._conn = None
        if self._error is not None:
            raise RuntimeError(f"Flux stream failed: {self._error}")
        if not settled:
            # Server never closed the turn (e.g. it heard only silence and
            # answered ForceEndTurn with a Warning). Fall back to the last
            # partial rather than failing the whole utterance.
            if self._last_partial:
                print(f"Flux: no EndOfTurn, falling back to last partial: "
                      f"{self._last_partial!r}", flush=True)
                return self._last_partial
            raise RuntimeError("Timed out waiting for Flux final transcript.")
        return self._transcript

    def abort(self) -> None:
        try:
            if self._cm is not None:
                self._cm.__exit__(None, None, None)
        except Exception:
            pass
        finally:
            self._conn = None
