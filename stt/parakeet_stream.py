"""Local streaming STT via parakeet-cli (offline, 120M EOU model).

Verified behavior of `parakeet-cli transcribe --model M --input - --stream`:
- stdin takes a WAV stream (header + PCM); use unknown sizes (0xFFFFFFFF)
  so the header can be written before the length is known.
- stdout lines: `[stream] <partial>` as speech decodes,
  `[stream] <text> [EOU @ Xs]` at end-of-utterance,
  `[stream:final] <text>` when the stream closes.
- Same duck-type interface as FluxStreamer: start/send_audio/finish/abort.
"""
import io
import re
import struct
import subprocess
import threading

EOU_PATTERN = re.compile(r"\s*\[EOU @ [^\]]+\]")


def wav_header_unknown_size() -> bytes:
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 0xFFFFFFFF, b"WAVE", b"fmt ", 16, 1, 1,
        16000, 32000, 2, 16, b"data", 0xFFFFFFFF,
    )


class ParakeetStreamSession:
    """One utterance = one instance. Not reusable across turns."""

    def __init__(self, binary_path: str, model_path: str):
        from pathlib import Path

        self.binary_path = Path(binary_path)
        self.model_path = Path(model_path)
        if not self.binary_path.exists():
            raise RuntimeError(f"parakeet-cli not found: {self.binary_path}")
        if not self.model_path.exists():
            raise RuntimeError(f"Streaming model not found: {self.model_path}")
        self._proc: subprocess.Popen | None = None
        self._final = threading.Event()
        self._transcript = ""
        self._last_partial = ""
        self._chunks_sent = 0
        self.on_partial = None

    def _reader(self):
        try:
            wrapper = io.TextIOWrapper(
                self._proc.stdout, encoding="utf-8", errors="replace")
            for line in wrapper:
                line = line.strip()
                if line.startswith("[stream:final]"):
                    self._transcript = line[len("[stream:final]"):].strip()
                    self._final.set()
                elif line.startswith("[stream]"):
                    text = EOU_PATTERN.sub("", line[len("[stream]"):]).strip()
                    if text:
                        self._last_partial = text
                        if self.on_partial:
                            try:
                                self.on_partial(text)
                            except Exception:
                                pass
                elif line:
                    print(f"parakeet-cli: {line}", flush=True)
        except Exception as exc:
            print(f"parakeet-cli reader ended: {exc}", flush=True)
        finally:
            self._final.set()  # never hang finish() if the process dies

    def start(self, on_partial=None) -> None:
        self.on_partial = on_partial
        self._proc = subprocess.Popen(
            [str(self.binary_path), "transcribe",
             "--model", str(self.model_path),
             "--input", "-", "--stream"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0,
        )
        try:
            self._proc.stdin.write(wav_header_unknown_size())
            self._proc.stdin.flush()
        except Exception as exc:
            raise RuntimeError(f"Could not write WAV header: {exc}") from exc
        threading.Thread(target=self._reader, daemon=True).start()

    def send_audio(self, chunk: bytes) -> None:
        if self._proc is not None and chunk:
            try:
                self._proc.stdin.write(chunk)
                self._proc.stdin.flush()
                self._chunks_sent += 1
            except (BrokenPipeError, ValueError) as exc:
                raise RuntimeError(f"parakeet-cli stdin closed: {exc}") from exc

    def finish(self, timeout: float = 30.0) -> str:
        if self._proc is None:
            raise RuntimeError("Stream session was never started.")
        print(f"parakeet-cli: {self._chunks_sent} chunks sent, closing stdin...",
              flush=True)
        try:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            settled = self._final.wait(timeout=timeout)
            try:
                self._proc.wait(timeout=5)
            except Exception:
                pass
        finally:
            self.abort()
        # Prefer an explicit final; else the last EOU/partial turn text.
        final = self._transcript or self._last_partial
        if final:
            if not settled:
                print("parakeet-cli: no clean final, using last partial.",
                      flush=True)
            return final
        raise RuntimeError("No transcript from local stream.")

    def abort(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
