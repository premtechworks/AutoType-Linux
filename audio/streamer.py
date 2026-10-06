"""Live 16 kHz mono 16-bit PCM chunk stream (no WAV file).

Feeds ~80 ms chunks (1280 samples = 2560 bytes) into a thread-safe queue
for streaming STT backends like Deepgram Flux.
"""
import queue
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_SAMPLES = 1280  # 80 ms at 16 kHz
CHUNK_BYTES = CHUNK_SAMPLES * 2


class MicrophoneStream:
    def __init__(self, device=None):
        self._configured_device = device  # None = resolve from config at start()
        self.streaming = False
        self.chunks: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self.stream = None
        self.level = 0.0
        self.active_device = None

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        if not self.streaming:
            return
        try:
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)) / 32768.0)
            self.level = min(1.0, rms * 5.0)
        except Exception:
            pass
        try:
            self.chunks.put_nowait(indata.tobytes())
        except queue.Full:
            pass  # drop oldest pace: never block the audio thread

    def start(self):
        from .devices import (
            capture_target_for,
            pipewire_capture_target,
            resolve_mic_device,
        )

        if self._configured_device is not None:
            device = self._configured_device
        else:
            try:
                import config
                device = resolve_mic_device(config.mic_device())
            except Exception:
                device = None
        target = capture_target_for(self._configured_device)
        self.chunks.queue.clear()
        self.level = 0.0
        self.streaming = True
        try:
            with pipewire_capture_target(target):
                self.stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype=DTYPE,
                    device=device,
                    blocksize=CHUNK_SAMPLES,
                    callback=self._callback,
                )
                self.stream.start()
        except Exception as exc:
            self.streaming = False
            self.stream = None
            raise RuntimeError(
                f"Could not open microphone ({device!r}): {exc}. "
                "Bluetooth headset? Switch its PipeWire profile to "
                "HSP/HFP (mSBC) in Settings → Microphone first — "
                "A2DP has no mic.") from exc
        self.active_device = device

    def read_chunk(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self.chunks.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        self.streaming = False
        self.level = 0.0
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
