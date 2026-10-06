"""OmniRoute text cleanup via OpenAI-compatible /v1/chat/completions (Bearer auth)."""
import requests

from .prompts import SYSTEM_PROMPT


class OmniRouteProcessor:
    def __init__(self, base_url: str, api_key: str, model: str = "auto",
                 temperature: float = 0.1):
        if not api_key:
            raise RuntimeError("Missing OMNIROUTE_API_KEY in .env.")
        self.url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    def process(self, transcript: str, system_prompt: str | None = None,
                user_payload: str | None = None) -> str:
        """Clean one utterance.

        `transcript` should already be deterministically normalized
        (llm/normalizer.py). Pass `user_payload` (built by
        prompts.build_user_payload) for structured context; otherwise the
        raw transcript is sent as the user message (backwards compat).
        """
        if not transcript.strip():
            return ""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                {"role": "user", "content": user_payload or transcript},
            ],
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                self.url, headers=headers, json=payload, timeout=60,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"OmniRoute request failed: {exc}") from exc

        data = response.json()
        try:
            result = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected OmniRoute response: {data}") from exc
        return (result or "").strip()
