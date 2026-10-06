"""Cloud STT via OpenAI-compatible /v1/audio/transcriptions endpoint.

Works with:
- OpenAI Whisper (https://api.openai.com/v1)
- Groq Cloud Whisper (https://api.groq.com/openai/v1) — ultra-fast <300ms
- NVIDIA NIM Cloud ASR (https://integrate.api.nvidia.com/v1)
- Any custom or self-hosted OpenAI-compatible transcription server
"""
from pathlib import Path

import requests

from .base import Transcriber


class CloudWhisperTranscriber(Transcriber):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
        language: str = "en",
    ):
        if not api_key:
            raise RuntimeError("Missing API key for Cloud STT. Configure it in Settings → Speech.")
        self.api_key = api_key
        self.model = model or "whisper-1"
        self.language = language or "en"

        clean_base = (base_url or "https://api.openai.com/v1").rstrip("/")
        if clean_base.endswith("/audio/transcriptions"):
            self.url = clean_base
        elif clean_base.endswith("/v1"):
            self.url = f"{clean_base}/audio/transcriptions"
        else:
            self.url = f"{clean_base}/v1/audio/transcriptions"

    def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        if path.stat().st_size < 1024:
            raise RuntimeError("Audio file is too small — nothing was recorded.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        data = {
            "model": self.model,
            "response_format": "json",
        }
        if self.language:
            data["language"] = self.language

        try:
            with path.open("rb") as audio_file:
                files = {
                    "file": (path.name, audio_file, "audio/wav"),
                }
                response = requests.post(
                    self.url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=60,
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Cloud STT request failed ({self.url}): {exc}") from exc

        payload = response.json()
        try:
            return payload.get("text", "").strip()
        except (AttributeError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Cloud STT response: {payload}") from exc
