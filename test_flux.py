"""Flux check: streams test.wav PCM in ~80 ms chunks, prints partials + final."""
import time
import wave

import config
from stt.flux import FluxStreamer

CHUNK = 2560  # 80 ms @16kHz linear16

with wave.open("test.wav", "rb") as wf:
    assert (wf.getframerate(), wf.getnchannels(), wf.getsampwidth()) == (16000, 1, 2), \
        "test.wav must be 16 kHz mono 16-bit"
    pcm = wf.readframes(wf.getnframes())

streamer = FluxStreamer(api_key=config.deepgram_api_key(), model=config.deepgram_flux_model())
streamer.start(on_partial=lambda t: print(f"partial: {t}", flush=True))

start = time.time()
for i in range(0, len(pcm), CHUNK):
    streamer.send_audio(pcm[i:i + CHUNK])
    time.sleep(0.02)  # paced faster than realtime is fine
time.sleep(0.3)  # let the last audio decode

final = streamer.finish(timeout=15.0)
print(f"\nFINAL ({time.time() - start:.1f}s after stream start):")
print(final if final else "(empty — no speech detected)")
