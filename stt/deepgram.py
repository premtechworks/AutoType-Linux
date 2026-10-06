"""Deepgram Nova batch STT over plain HTTP (no SDK)."""
from pathlib import Path

import requests

from .base import Transcriber


class DeepgramTranscriber(Transcriber):
    def __init__(self, api_key: str, model: str = "nova-3", language: str = "en-US"):
        if not api_key:
            raise RuntimeError("Missing DEEPGRAM_API_KEY in .env.")
        self.api_key = api_key
        self.model = model
        self.language = language

    def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        if path.stat().st_size < 1024:
            raise RuntimeError("Audio file is too small — nothing was recorded.")

        url = "https://api.deepgram.com/v1/listen"
        params = {
            "model": self.model,
            "language": self.language,
            "smart_format": "true",
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav",
        }
        try:
            with path.open("rb") as audio_file:
                response = requests.post(
                    url, params=params, headers=headers,
                    data=audio_file, timeout=60,
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Deepgram request failed: {exc}") from exc

        payload = response.json()
        try:
            return (
                payload["results"]["channels"][0]
                ["alternatives"][0]["transcript"]
            ).strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError(f"Unexpected Deepgram response: {payload}") from exc
