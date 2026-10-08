"""16 kHz mono 16-bit microphone capture."""
import threading
import wave

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


class Recorder:
    def __init__(self, device=None):
        self._configured_device = device  # None = resolve from config at start()
        self.recording = False
        self.frames: list[np.ndarray] = []
        self.stream = None
        self.lock = threading.Lock()
        self.level = 0.0  # 0..1 live mic level for the overlay waveform
        self.active_device = None  # resolved sounddevice device actually used

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        if self.recording:
            with self.lock:
                self.frames.append(indata.copy())
            # RMS level, scaled so normal speech moves the bars.
            try:
                rms = float(
                    np.sqrt(np.mean(indata.astype(np.float32) ** 2)) / 32768.0
                )
                self.level = min(1.0, rms * 5.0)
            except Exception:
                pass

    def start(self):
        # Resolve the mic now (not in __init__) so settings changes and
        # Bluetooth (dis)connections apply to every new utterance.
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
        with self.lock:
            self.frames.clear()
        self.level = 0.0
        self.recording = True
        try:
            with pipewire_capture_target(target):
                self.stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype=DTYPE,
                    device=device,
                    callback=self._callback,
                )
                self.stream.start()
        except Exception as exc:
            self.recording = False
            self.stream = None
            raise RuntimeError(
                f"Could not open microphone ({device!r}): {exc}. "
                "Bluetooth headset? Switch its PipeWire profile to "
                "HSP/HFP (mSBC) in Settings → Microphone first — "
                "A2DP has no mic.") from exc
        self.active_device = device

    def stop(self, output_path: str) -> str:
        self.recording = False
        self.level = 0.0
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        with self.lock:
            if not self.frames:
                raise RuntimeError("No audio was recorded.")
            audio = np.concatenate(self.frames, axis=0)
            if np.abs(audio).max() == 0:
                raise RuntimeError("No audio was recorded (silence only).")
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return output_path

    def abort(self) -> None:
        self.recording = False
        self.level = 0.0
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        with self.lock:
            self.frames.clear()

