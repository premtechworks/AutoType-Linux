"""Personal vocabulary: exact terms passed into the cleaning prompt."""
import json
from pathlib import Path


def load_terms(path: Path) -> list[str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        terms = data.get("terms", []) if isinstance(data, dict) else []
        return [t.strip() for t in terms if isinstance(t, str) and t.strip()]
    except Exception:
        return []


def with_vocabulary(base_prompt: str, terms: list[str]) -> str:
    if not terms:
        return base_prompt
    block = (
        "\nUser vocabulary — when the speech sounds like one of these, "
        "always use this exact spelling (high confidence only; "
        "never guess a vocab term for an unrelated word):\n"
        + "\n".join(f"- {t}" for t in terms)
    )
    return base_prompt + block


def fix_vocabulary_casing(text: str, terms: list[str]) -> str:
    """Deterministic high-confidence vocab fix (no LLM needed).

    Delegates to llm.normalizer so casing like "power bi" -> "Power BI"
    is fixed even when the LLM is bypassed or fails. Import is lazy to
    avoid a hard import cycle.
    """
    if not text or not terms:
        return text
    from .normalizer import apply_vocabulary_casing
    return apply_vocabulary_casing(text, terms)
