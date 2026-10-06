"""Backwards-compatibility alias for LLMProcessor.

Previously AutoType only supported OmniRoute as the cleanup provider.
AutoType now supports any API provider (OpenAI, Anthropic Claude, Grok,
DeepSeek, Qwen, NVIDIA NIM, Groq, Ollama, Custom/OmniRoute).
See llm/processor.py for the full implementation.
"""
from .processor import LLMProcessor, LLMProcessor as OmniRouteProcessor

__all__ = ["OmniRouteProcessor", "LLMProcessor"]
