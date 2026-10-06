"""AutoType: double-tap Right Alt → Deepgram → OmniRoute → clipboard paste.

Runs as a silent background daemon: no terminal needed. A floating
pill widget above the taskbar shows recording / working states.
"""
import logging
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk
from pynput import keyboard

import config
from audio.recorder import Recorder
from audio.streamer import MicrophoneStream
from context.commands import detect_command
from context.history import History
from desktop.clipboard import get_selected_text, insert_text
from desktop.notifications import APP_NAME, notify
from llm.normalizer import normalize_transcript
from llm.omniroute import OmniRouteProcessor
from llm.prompts import (
    MODES,
    SYSTEM_PROMPT,
    build_system_prompt,
    build_user_payload,
    is_code_like,
    resolve_mode,
)
from llm.vocabulary import fix_vocabulary_casing, load_terms, with_vocabulary
from stt.factory import create_transcriber
from ui.overlay import Overlay
from utils.log import setup_logging

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "recordings"
AUDIO_DIR.mkdir(exist_ok=True)

log = logging.getLogger("autotype")


class AutoType:
    def __init__(self, overlay=None):
        self.overlay = overlay
        self.recorder = Recorder()
        self.transcriber = create_transcriber()
        self.processor = OmniRouteProcessor(
            base_url=config.omniroute_base_url(),
            api_key=config.omniroute_api_key(),
            model=config.omniroute_model(),
            temperature=config.cleaning_temperature(),
        )
        self.is_recording = False
        self.busy = False  # True while transcribe/process/paste runs
        self.streaming = False  # True while a Flux stream session is open
        # Streaming STT for toggle: deepgram (Flux) and parakeet_stream
        # (local 120M EOU). Batch-only backends use WAV recording.
        self.use_streaming = config.stt_backend() in ("deepgram", "parakeet_stream")
        self.processing_mode = config.processing_mode()  # raw | clean | smart
        self.backend = config.stt_backend()
        self.history = History(BASE_DIR / "data" / "history.jsonl")
        self.tray = None
        self.lock = threading.Lock()
        # Stream session state (only touched by stream methods).
        self._stream_mic: MicrophoneStream | None = None
        self._stream_session = None
        self._stream_sending = threading.Event()

    def current_level(self) -> float:
        """Live mic level for the overlay waveform (either capture mode)."""
        try:
            if self._stream_mic is not None and self.streaming:
                return self._stream_mic.level
            return self.recorder.level
        except Exception:
            return 0.0

    def set_processing_mode(self, mode: str) -> None:
        mode = mode.strip().lower()
        if mode not in MODES:
            return
        self.processing_mode = mode
        log.info(f"Processing mode: {mode}")

    # -- UI helpers (overlay pill + tray icon stay in sync) --------------
    def _ui_recording(self):
        if self.overlay:
            self.overlay.show_recording()
        if self.tray:
            self.tray.set_state("recording")

    def _ui_processing(self, text: str):
        if self.overlay:
            self.overlay.show_processing(text)
        if self.tray:
            self.tray.set_state("processing")

    def _ui_done(self):
        if self.overlay:
            self.overlay.hide()
        if self.tray:
            self.tray.flash_ready()

    def _ui_error(self, message: str):
        log.warning(message)
        if self.overlay:
            self.overlay.show_error(message)
        if self.tray:
            self.tray.set_state("error")
        if not self.overlay and not self.tray:
            notify(APP_NAME, message)

    def start_recording(self):
        with self.lock:
            if self.busy or self.is_recording:
                return
            self.is_recording = True
        try:
            self.recorder.start()
            self._t_start = time.monotonic()
            log.info("Recording... (double-tap Right Alt to stop)")
            self._ui_recording()
        except Exception as exc:
            with self.lock:
                self.is_recording = False
            self._ui_error(f"Recording error: {exc}")

    def _capture_audio(self) -> Path:
        """Save the utterance to WAV. Persistent only if SAVE_RECORDINGS=true."""
        import tempfile

        if config.save_recordings():
            timestamp = int(time.time() * 1000)
            audio_path = AUDIO_DIR / f"{timestamp}.wav"
        else:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".wav", prefix="autotype-", delete=False,
            )
            tmp.close()
            audio_path = Path(tmp.name)
        self.recorder.stop(str(audio_path))
        return audio_path

    def _cleanup_audio(self, audio_path: Path) -> None:
        if not config.save_recordings():
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

    def stop_and_process(self):
        with self.lock:
            if not self.is_recording:
                return
            self.is_recording = False
            self.busy = True
        try:
            self._ui_processing("Transcribing...")
            t_stop = time.monotonic()
            audio_path = self._capture_audio()
            log.info(f"Audio captured: {audio_path}")

            log.info("-> Transcribing...")
            t0 = time.monotonic()
            try:
                transcript = self.transcriber.transcribe(str(audio_path))
            finally:
                self._cleanup_audio(audio_path)
            stt_dur = time.monotonic() - t0
            record_dur = t_stop - getattr(self, "_t_start", t_stop)
            log.info(f"RAW: {transcript}")
            if not transcript:
                self._ui_error("No speech detected.")
                return

            self.process_and_insert(transcript, record_dur, stt_dur)
        except Exception as exc:
            self._ui_error(f"Error: {exc}")
        finally:
            with self.lock:
                self.busy = False

    def process_and_insert(self, transcript: str,
                           record_dur: float = 0.0,
                           stt_dur: float = 0.0) -> None:
        """4-layer pipeline: STT -> NORMALIZER -> INTELLIGENCE -> INPUT.

        1. Voice commands (strict prefix match, never eats dictation).
        2. Deterministic normalizer (spoken punctuation, lists, vocab casing).
        3. OmniRoute LLM with structured payload (mode/app/selection/history).
        4. Clipboard paste + history.
        """
        t_after_stop = time.monotonic()
        raw_transcript = transcript
        mode = self.processing_mode

        # -- layer 0: voice commands (on the untouched STT text) ---------
        command = detect_command(raw_transcript, config.command_prefix())
        if command is not None and command["action"] == "cancel":
            log.info("Voice command: cancel — discarding utterance.")
            self.history.append({"mode": mode, "backend": self.backend,
                                 "raw": raw_transcript, "final": "",
                                 "cancelled": True})
            self._ui_done()
            return
        if command is not None and command["action"] == "mode":
            mode = command["mode"]
            transcript = command["text"]
            log.info(f"Voice command: one-shot mode={mode}.")
            if not transcript:
                self._ui_error("No text after mode command.")
                return

        profile, app_label = "prose", ""
        try:
            from desktop.profiles import detect_profile
            profile, app_label = detect_profile()
        except Exception:
            pass

        terms = load_terms(BASE_DIR / "data" / "vocabulary.json")

        # -- layer 1: deterministic normalizer (no LLM, no guessing) -----
        normalized = normalize_transcript(transcript, terms)
        if not normalized:
            normalized = transcript.strip()
        log.info(f"NORMALIZED: {normalized}")

        # -- RAW mode: minimal LLM-free path (vocab casing only) ---------
        if mode == "raw":
            final_text = fix_vocabulary_casing(normalized, terms)
            llm_dur = 0.0
            log.info("Mode=raw: skipping LLM.")
        else:
            # Code-like speech routes to CODE style (literal) instead of
            # being prose-ified; the LLM still runs for code mode.
            effective = resolve_mode(mode, profile)
            if is_code_like(normalized) and mode in ("clean", "smart"):
                effective = "code"
                log.info("Code-like speech detected -> CODE style.")
            # -- layer 2 context: selection + continuity ----------------
            try:
                selected = get_selected_text()
            except Exception:
                selected = ""
            # Don't let a huge selection blow up the prompt.
            if len(selected) > 1500:
                selected = selected[:1500]
            try:
                recent = self.history.recent_finals(1)
                previous = recent[0] if recent else ""
            except Exception:
                previous = ""
            if config.use_custom_prompt() and config.custom_prompt() \
                    and effective in ("clean", "code"):
                system_prompt = config.custom_prompt()
                log.info(f"Mode={effective} (custom prompt).")
            else:
                system_prompt = build_system_prompt(effective, profile,
                                                    app_label)
                log.info(f"Mode={mode} -> {effective} (profile={profile}).")
            system_prompt = with_vocabulary(system_prompt, terms)
            user_payload = build_user_payload(
                normalized, mode=effective, application=app_label,
                selected_text=selected, previous_text=previous,
                vocabulary=terms)
            self._ui_processing("Cleaning...")
            log.info("-> Processing with OmniRoute...")
            t0 = time.monotonic()
            try:
                final_text = self.processor.process(
                    normalized, system_prompt, user_payload=user_payload)
                final_text = self._validate_output(final_text, normalized)
            except Exception as exc:
                log.warning(f"OmniRoute failed, using normalized text: {exc}")
                final_text = normalized
            llm_dur = time.monotonic() - t0

        log.info(f"FINAL: {final_text}")
        if not final_text:
            self._ui_error("No text generated.")
            return

        t0 = time.monotonic()
        insert_text(final_text)
        insert_dur = time.monotonic() - t0
        self._ui_done()
        after_stop = t_after_stop and (time.monotonic() - t_after_stop)
        log.info(
            f"Timing: record={record_dur:.1f}s stt={stt_dur:.2f}s "
            f"llm={llm_dur:.2f}s insert={insert_dur:.2f}s "
            f"(after-stop total={after_stop:.2f}s)")
        self.history.append({"mode": mode, "backend": self.backend,
                             "app": app_label, "profile": profile,
                             "raw": raw_transcript,
                             "normalized": normalized
                             if "normalized" in dir() else transcript,
                             "final": final_text,
                             "timing": {"record": round(record_dur, 2),
                                        "stt": round(stt_dur, 2),
                                        "llm": round(llm_dur, 2),
                                        "insert": round(insert_dur, 2)}})

    @staticmethod
    def _validate_output(final_text: str, fallback: str) -> str:
        """Guard against LLM wrapper/hallucination artifacts.

        Strips surrounding quotes, 'Here is your text:' preambles and
        code fences. Falls back to the normalized text when the LLM
        returns nothing usable or an absurdly long blob (>10x input,
        min 2000 chars — sign of a runaway rewrite).
        """
        text = (final_text or "").strip()
        # Strip chatty preambles ("Here is the cleaned text: ...").
        text = __import__("re").sub(
            r"^(?:here (?:is|are)[^:\n]*:|cleaned text:|result:)\s*",
            "", text, flags=__import__("re").IGNORECASE).strip()
        # Strip one layer of surrounding quotes / code fences.
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            text = text[1:-1].strip()
        if text.startswith("```"):
            text = __import__("re").sub(
                r"^```\w*\n?", "", text)
            text = __import__("re").sub(r"\n?```$", "", text).strip()
        if not text:
            return fallback
        if len(text) > max(2000, len(fallback) * 10):
            log.warning("LLM output suspiciously long; using normalized text.")
            return fallback
        return text

    def toggle(self):
        # Never block the hotkey listener: slow work runs in a thread.
        if self.streaming:
            threading.Thread(target=self.stop_stream, daemon=True).start()
        elif self.is_recording:
            threading.Thread(target=self.stop_and_process, daemon=True).start()
        elif self.busy:
            return
        elif self.use_streaming:
            self.start_stream()
        else:
            self.start_recording()

    # -- streaming toggle (Flux, no WAV file) -----------------------------
    def start_stream(self):
        """Double-tap Right Alt: open stream session, mic chunks flow straight to it."""
        with self.lock:
            if self.busy or self.is_recording or self.streaming:
                return
            self.streaming = True
        try:
            from stt.factory import create_stream_session

            log.info(f"Stream engine: {config.stt_backend()}")
            session = create_stream_session(on_partial=self._on_stream_partial)
        except Exception as exc:
            with self.lock:
                self.streaming = False
            self._ui_error(f"Stream failed: {exc}")
            return
        try:
            mic = MicrophoneStream()
            mic.start()
        except Exception as exc:
            session.abort()
            with self.lock:
                self.streaming = False
            self._ui_error(f"Microphone error: {exc}")
            return
        self._stream_session = session
        self._stream_mic = mic
        # Stream dumps are gated behind SAVE_RECORDINGS (see _dump_stream_audio).
        self._stream_frames: list[bytes] = []
        self._stream_chunks = 0
        self._stream_peak = 0.0
        self._stream_first_size = 0
        self._stream_sending.set()
        self._t_start = time.monotonic()
        log.info("Streaming... (double-tap Right Alt to stop)")
        self._ui_recording()
        self._stream_pump = threading.Thread(target=self._pump_stream_audio, daemon=True)
        self._stream_pump.start()

    def _pump_stream_audio(self):
        """Mic thread -> Flux socket, ~80 ms chunks, memory only."""
        while self._stream_sending.is_set():
            chunk = self._stream_mic.read_chunk(timeout=0.5)
            if chunk is None:
                continue
            self._stream_chunks += 1
            if self._stream_first_size == 0:
                self._stream_first_size = len(chunk)
            try:
                self._stream_peak = max(self._stream_peak, self._stream_mic.level)
            except Exception:
                pass
            if self._stream_frames is not None:
                self._stream_frames.append(chunk)
            if self._stream_session is not None:
                try:
                    self._stream_session.send_audio(chunk)
                except Exception as exc:
                    log.warning(f"Stream send failed: {exc}")
                    break

    def _on_stream_partial(self, text: str):
        if self.overlay:
            self.overlay.update_partial(text)

    def _dump_stream_audio(self) -> str:
        """Write the exact bytes sent to Flux as a WAV (debug when enabled)."""
        if not config.save_recordings():
            self._stream_frames = []
            return ""
        frames = self._stream_frames
        self._stream_frames = []
        if not frames:
            return ""
        import wave

        from audio.streamer import CHANNELS, SAMPLE_RATE

        timestamp = int(time.time() * 1000)
        path = AUDIO_DIR / f"stream-{timestamp}.wav"
        try:
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(frames))
            return str(path)
        except Exception as exc:
            log.warning(f"Stream dump failed: {exc}")
            return ""

    def stop_stream(self):
        """Second double-tap: finalize turn -> clean -> paste."""
        with self.lock:
            if not self.streaming:
                return
            self.streaming = False
            self.busy = True
        self._stream_sending.clear()
        try:
            if self._stream_mic is not None:
                self._stream_mic.stop()
            # Wait for the pump thread so stats below are final, not stale.
            pump = getattr(self, "_stream_pump", None)
            if pump is not None:
                pump.join(timeout=2.0)
            self._ui_processing("Transcribing...")
            chunks = self._stream_chunks
            peak = self._stream_peak
            t_stop = time.monotonic()
            log.info(f"Stream audio: {chunks} chunks (~{chunks * 0.08:.1f}s), "
                     f"first chunk {self._stream_first_size} bytes, "
                     f"mic peak level {peak:.2f}")
            dump = self._dump_stream_audio()
            if dump:
                log.info(f"Stream audio dumped: {dump} (play with: aplay {dump})")
            log.info("-> Finalizing turn...")
            t0 = time.monotonic()
            transcript = self._stream_session.finish()
            stt_dur = time.monotonic() - t0
            record_dur = t_stop - getattr(self, "_t_start", t_stop)
            log.info(f"RAW: {transcript}")
            if not transcript:
                self._ui_error("No speech detected.")
                return
            self.process_and_insert(transcript, record_dur, stt_dur)
        except Exception as exc:
            self._ui_error(f"Error: {exc}")
        finally:
            try:
                if self._stream_session is not None:
                    self._stream_session.abort()
            except Exception:
                pass
            self._stream_session = None
            self._stream_mic = None
            with self.lock:
                self.busy = False


def main():
    setup_logging(BASE_DIR / "logs")
    import os
    try:
        (BASE_DIR / "data" / "daemon.pid").write_text(str(os.getpid()))
    except Exception:
        pass
    try:
        app = AutoType()
    except RuntimeError as exc:
        # Missing keys / bad .env: clear message, no traceback crash.
        log.error(exc)
        notify(APP_NAME, str(exc))
        raise SystemExit(1)

    # Overlay lives on the GTK (main) thread; it polls the live mic level.
    app.overlay = Overlay(get_level=lambda: app.current_level())

    # Tray icon: state colors + mode menu. Runs detached in its own thread.
    from ui.tray import TrayController

    tray = TrayController(
        get_mode=lambda: app.processing_mode,
        set_mode=app.set_processing_mode,
        backend=config.stt_backend(),
        on_quit=Gtk.main_quit,
    )
    app.tray = tray
    tray.run()

    log.info("=" * 50)
    log.info(f"{APP_NAME} backend={app.backend} mode={app.processing_mode}")
    log.info("Double-tap Right Alt to start/stop recording.")

    # Double-tap detection: two fresh Right-Alt presses within this window.
    # This is the only trigger: start and stop use the same gesture.
    DOUBLE_TAP_WINDOW = 0.4
    RIGHT_ALT_KEYS = {keyboard.Key.alt_r, keyboard.Key.alt_gr}
    last_tap = [0.0]
    held = set()

    def on_press(key):
        if key in RIGHT_ALT_KEYS:
            if key in held:
                return  # key auto-repeat while held — not a new tap
            held.add(key)
            now = time.monotonic()
            if now - last_tap[0] < DOUBLE_TAP_WINDOW:
                last_tap[0] = 0.0
                app.toggle()
            else:
                last_tap[0] = now

    def on_release(key):
        held.discard(key)

    def make_listener():
        return keyboard.Listener(on_press=on_press, on_release=on_release)

    state = {"listener": make_listener()}
    state["listener"].start()

    def watchdog():
        """Recovery: restart the hotkey listener if it ever dies."""
        while True:
            time.sleep(30)
            try:
                if not state["listener"].is_alive():
                    log.warning("Hotkey listener died; restarting.")
                    state["listener"] = make_listener()
                    state["listener"].start()
            except Exception as exc:
                log.warning(f"Listener watchdog failed: {exc}")

    threading.Thread(target=watchdog, daemon=True).start()
    log.info("AutoType daemon running. Double-tap Right Alt anywhere.")
    try:
        Gtk.main()  # main thread idles here; ~0% CPU until events arrive
    except KeyboardInterrupt:
        log.info("Exiting...")
    finally:
        try:
            state["listener"].stop()
        except Exception:
            pass
        try:
            (BASE_DIR / "data" / "daemon.pid").unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
