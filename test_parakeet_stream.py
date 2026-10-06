"""Local stream check: feeds test.wav PCM through ParakeetStreamSession paced live."""
import time
import wave

import config
from stt.parakeet_stream import ParakeetStreamSession

CHUNK = 2560  # 80 ms @16kHz linear16

with wave.open("test.wav", "rb") as wf:
    assert (wf.getframerate(), wf.getnchannels(), wf.getsampwidth()) == (16000, 1, 2), \
        "test.wav must be 16 kHz mono 16-bit"
    pcm = wf.readframes(wf.getnframes())

session = ParakeetStreamSession(
    binary_path=config.parakeet_stream_binary(),
    model_path=config.parakeet_stream_model(),
)
session.start(on_partial=lambda t: print(f"partial: {t}", flush=True))

start = time.time()
for i in range(0, len(pcm), CHUNK):
    session.send_audio(pcm[i:i + CHUNK])
    time.sleep(0.08)  # realtime pace, like the mic pump

final = session.finish()
print(f"\nFINAL ({time.time() - start:.1f}s session):")
print(final if final else "(empty — no speech detected)")
