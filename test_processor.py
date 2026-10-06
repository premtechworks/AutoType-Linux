"""LLM text cleaning check: cleans a sample transcript using active provider from .env."""
import config
from llm.processor import LLMProcessor

print(f"Testing LLM Cleaner:")
print(f"  Provider:    {config.llm_provider().upper()}")
print(f"  Base URL:    {config.llm_base_url()}")
print(f"  Model:       {config.llm_model()}")
print(f"  Temperature: {config.cleaning_temperature()}")

processor = LLMProcessor(
    base_url=config.llm_base_url(),
    api_key=config.llm_api_key(),
    model=config.llm_model(),
    provider=config.llm_provider(),
    temperature=config.cleaning_temperature(),
)

text = """
hey can you write a message saying hi rahul
i finished the sales dashboard and i need you to check
the revenue calculation before tomorrow morning
"""

print("\nINPUT TRANSCRIPT:")
print(text.strip())

result = processor.process(text)

print("\nPROCESSED OUTPUT:")
print(result)
