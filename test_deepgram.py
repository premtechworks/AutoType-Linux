"""Deepgram check: transcribes test.wav (needs .env with DEEPGRAM_API_KEY)."""
import config
from stt.deepgram import DeepgramTranscriber

transcriber = DeepgramTranscriber(
    api_key=config.deepgram_api_key(),
    model=config.deepgram_model(),
    language=config.deepgram_language(),
)
text = transcriber.transcribe("test.wav")

print("\nTRANSCRIPT:")
print(text if text else "(empty — no speech detected)")
