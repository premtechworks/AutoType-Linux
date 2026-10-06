"""OmniRoute check: cleans a sample transcript (needs .env with OMNIROUTE_*)."""
import config
from llm.omniroute import OmniRouteProcessor

processor = OmniRouteProcessor(
    base_url=config.omniroute_base_url(),
    api_key=config.omniroute_api_key(),
    model=config.omniroute_model(),
)

text = """
hey can you write a message saying hi rahul
i finished the sales dashboard and i need you to check
the revenue calculation before tomorrow morning
"""

result = processor.process(text)

print("\nPROCESSED TEXT:")
print(result)
