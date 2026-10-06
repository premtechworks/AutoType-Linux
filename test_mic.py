"""Mic check: records 5 s of 16 kHz mono audio to test.wav."""
import wave

import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
SECONDS = 5
OUTPUT = "test.wav"

print("Recording for 5 seconds... speak now.")
audio = sd.rec(
    int(SECONDS * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype="int16",
)
sd.wait()

with wave.open(OUTPUT, "wb") as wf:
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)
    wf.setframerate(SAMPLE_RATE)
    wf.writeframes(audio.tobytes())

print(f"Saved {OUTPUT} — play it with: aplay {OUTPUT}")
