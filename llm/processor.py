"""Vendor-agnostic LLM text cleanup processor.

Supports all major API providers:
- OpenAI (ChatGPT)
- Anthropic (Claude)
- xAI (Grok)
- DeepSeek
- Qwen (Alibaba DashScope)
- NVIDIA NIM
- Groq
- OpenRouter
- Ollama (Local)
- Custom API Provider (e.g. OmniRoute, vLLM, LM Studio, self-hosted proxy)
"""
from __future__ import annotations

import logging
import requests

from .prompts import SYSTEM_PROMPT

log = logging.getLogger("autotype")

# Standard defaults for popular providers
PROVIDER_CONFIGS: dict[str, dict[str, str]] = {
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "protocol": "openai",
        "help": "Use an OpenAI API key (sk-...). Recommended model: gpt-4o-mini.",
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-20241022",
        "protocol": "anthropic",
        "help": "Use an Anthropic API key (sk-ant-...). Recommended model: claude-3-5-haiku-20241022.",
    },
    "xai": {
        "name": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-2-mini",
        "protocol": "openai",
        "help": "Use an xAI API key. Recommended model: grok-2-mini or grok-2.",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "protocol": "openai",
        "help": "Use a DeepSeek API key. Recommended model: deepseek-chat.",
    },
    "qwen": {
        "name": "Qwen (Alibaba DashScope)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "protocol": "openai",
        "help": "Use an Alibaba DashScope API key. Recommended model: qwen-plus or qwen-turbo.",
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "meta/llama-3.3-70b-instruct",
        "protocol": "openai",
        "help": "Use an NVIDIA build API key (nvapi-...). Recommended model: meta/llama-3.3-70b-instruct.",
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "protocol": "openai",
        "help": "Ultra-fast inference. Recommended model: llama-3.3-70b-versatile or llama-3.1-8b-instant.",
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "protocol": "openai",
        "help": "Aggregated models. Use any model identifier from OpenRouter.",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "protocol": "openai",
        "help": "Local offline LLM running via Ollama. No API key required.",
    },
    "custom": {
        "name": "Custom API Provider (e.g. OmniRoute)",
        "base_url": "http://127.0.0.1:20128/v1",
        "default_model": "auto",
        "protocol": "openai",
        "help": "Any OpenAI-compatible endpoint (OmniRoute, vLLM, LM Studio, self-hosted proxy).",
    },
}


def normalize_provider(name: str | None) -> str:
    """Map user-entered provider string to canonical key."""
    if not name:
        return "custom"
    key = name.strip().lower()
    # Common aliases
    if "claude" in key or "anthropic" in key:
        return "anthropic"
    if "grok" in key or "xai" in key or "x-ai" in key:
        return "xai"
    if "deepseek" in key:
        return "deepseek"
    if "qwen" in key or "dashscope" in key:
        return "qwen"
    if "nvidia" in key or "nim" in key:
        return "nvidia"
    if "groq" in key:
        return "groq"
    if "openrouter" in key:
        return "openrouter"
    if "ollama" in key:
        return "ollama"
    if "openai" in key or "chatgpt" in key:
        return "openai"
    if "omniroute" in key:
        return "custom"
    if key in PROVIDER_CONFIGS:
        return key
    return "custom"


class LLMProcessor:
    """Universal text cleaner supporting OpenAI-compatible and Anthropic APIs."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        provider: str = "custom",
        temperature: float = 0.1,
    ):
        self.provider = normalize_provider(provider)
        cfg = PROVIDER_CONFIGS.get(self.provider, PROVIDER_CONFIGS["custom"])

        self.base_url = (base_url or cfg["base_url"]).rstrip("/")
        self.api_key = api_key or ""
        self.model = model or cfg["default_model"]
        self.temperature = float(temperature)

        # Detect protocol: Anthropic Messages API vs OpenAI Chat Completions
        if self.provider == "anthropic" or "api.anthropic.com" in self.base_url:
            self.protocol = "anthropic"
        else:
            self.protocol = "openai"

    def process(
        self,
        transcript: str,
        system_prompt: str | None = None,
        user_payload: str | None = None,
    ) -> str:
        """Clean one utterance.

        transcript should already be deterministically normalized
        (llm/normalizer.py). Pass user_payload for structured context.
        """
        if not transcript.strip():
            return ""

        sys_prompt = system_prompt or SYSTEM_PROMPT
        usr_content = user_payload or transcript

        if self.protocol == "anthropic":
            return self._process_anthropic(sys_prompt, usr_content)
        return self._process_openai(sys_prompt, usr_content)

    def _process_openai(self, system_prompt: str, user_content: str) -> str:
        """Standard OpenAI-compatible /v1/chat/completions endpoint."""
        base = self.base_url
        if base.endswith("/chat/completions"):
            endpoint_url = base
        elif base.endswith("/v1"):
            endpoint_url = f"{base}/chat/completions"
        else:
            endpoint_url = f"{base}/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": self.temperature,
        }

        try:
            response = requests.post(
                endpoint_url, headers=headers, json=payload, timeout=60,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            provider_name = PROVIDER_CONFIGS.get(self.provider, {}).get("name", self.provider)
            raise RuntimeError(f"{provider_name} request failed: {exc}") from exc

        data = response.json()
        try:
            result = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected response from {endpoint_url}: {data}") from exc
        return (result or "").strip()

    def _process_anthropic(self, system_prompt: str, user_content: str) -> str:
        """Anthropic Messages API (/v1/messages)."""
        base = self.base_url
        if base.endswith("/messages"):
            endpoint_url = base
        elif base.endswith("/v1"):
            endpoint_url = f"{base}/messages"
        else:
            endpoint_url = f"{base}/v1/messages"

        if not self.api_key:
            raise RuntimeError("Missing Anthropic API key. Add it in Settings → Cleaning.")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_content},
            ],
            "temperature": self.temperature,
        }

        try:
            response = requests.post(
                endpoint_url, headers=headers, json=payload, timeout=60,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Anthropic request failed: {exc}") from exc

        data = response.json()
        try:
            # Format: {"content": [{"type": "text", "text": "..."}]}
            text_blocks = [
                b.get("text", "") for b in data.get("content", [])
                if b.get("type") == "text"
            ]
            result = "".join(text_blocks)
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Anthropic response: {data}") from exc
        return (result or "").strip()
