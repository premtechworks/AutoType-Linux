"""Deterministic normalizer — layer 2 of the Wispr-Flow-style pipeline.

Architecture (see docs):
    VOICE -> STT ENGINE -> NORMALIZER (here, cheap + deterministic)
            -> INTELLIGENCE (OmniRoute LLM) -> INPUT LAYER (clipboard)

Everything in this module is rule-based Python: no network, no LLM,
no guessing. The LLM later handles ambiguous punctuation, filler
removal, grammar, tone and semantic rewriting.

Handles (concepts #9, #10, #26):
  - spoken punctuation: "comma", "period", "question mark", ...
  - structural commands: "new paragraph", "new line", "open/close quote"
  - list formatting: "bullet point ...", "numbered list ... first/second/..."
  - whitespace / repeated-word cleanup
  - deterministic personal-vocabulary casing fix (high-confidence only)
"""
from __future__ import annotations

import re

# -- spoken punctuation ----------------------------------------------------
# Order matters: longest phrases first so "question mark" wins over "mark".
_PUNCT_MAP: tuple[tuple[str, str], ...] = (
    ("question mark", "?"),
    ("exclamation mark", "!"),
    ("exclamation point", "!"),
    ("open quote", "\u201c"),
    ("close quote", "\u201d"),
    ("open paren", "("),
    ("close paren", ")"),
    ("open bracket", "["),
    ("close bracket", "]"),
    ("colon", ":"),
    ("semicolon", ";"),
    ("comma", ","),
    ("period", "."),
    ("full stop", "."),
    ("ellipsis", "\u2026"),
    ("dash", "-"),
    ("hyphen", "-"),
)

# Structural commands that become whitespace, handled before punctuation
# so "new paragraph" is not mangled into "...new period...".
_PARA_RE = re.compile(r"\bnew\s+paragraphs?\b", re.IGNORECASE)
_NEWLINE_RE = re.compile(r"\bnew\s+lines?\b", re.IGNORECASE)

# List triggers
_BULLET_RE = re.compile(r"\bbullet\s+points?\b", re.IGNORECASE)
_NUMBERED_TRIGGERS = (
    "numbered list",
    "number list",
    "ordered list",
)
_ORDINAL_SPLIT_RE = re.compile(
    r"\b(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|"
    r"sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|"
    r"next|then|finally|lastly)\b[,:]?\s*",
    re.IGNORECASE,
)

# "make this a numbered list" / "make this a bullet list" preamble strip
_LIST_PREAMBLE_RE = re.compile(
    r"^\s*(?:please\s+)?make\s+this\s+(?:a\s+)?"
    r"(?:numbered|number|ordered|bullet(?:ed)?)\s+list\s*[:,.]?\s*",
    re.IGNORECASE,
)

_REPEATED_WORD_RE = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _protect_structural_markers(text: str) -> tuple[str, dict[str, str]]:
    """Replace new-paragraph/new-line with private-use placeholders.

    Returns (protected_text, table) so punctuation replacement cannot
    touch them; caller restores via _restore_structural_markers.
    """
    table: dict[str, str] = {}
    text = _PARA_RE.sub("\ue000", text)
    text = _NEWLINE_RE.sub("\ue001", text)
    return text, table


def _restore_structural_markers(text: str) -> str:
    return text.replace("\ue000", "\n\n").replace("\ue001", "\n")


def interpret_spoken_punctuation(text: str, structural: bool = True) -> str:
    """Replace spoken punctuation words with symbols (case-insensitive).

    Only matches whole words with word boundaries, so "comment" does not
    become "com,ment" and "periodical" is untouched. Set structural=False
    to leave "new paragraph / new line" as plain words (used for already
    list-formatted lines where re-interpreting them would corrupt markers).
    """
    if not text:
        return text
    if structural:
        text, _ = _protect_structural_markers(text)
    else:
        text = _PARA_RE.sub(" ", text)
        text = _NEWLINE_RE.sub(" ", text)
    for phrase, symbol in _PUNCT_MAP:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        # Pad symbols that need spacing care; final whitespace pass cleans up.
        text = pattern.sub(f" {symbol} ", text)
    text = _restore_structural_markers(text)
    # Tidy spaces around punctuation: "hello , world ." -> "hello, world."
    text = re.sub(r"\s+([,.;:!?)\]}…])", r"\1", text)
    text = re.sub(r"([(\[{“])\s+", r"\1", text)
    text = re.sub(r"\s+([”])", r"\1", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    # Collapse accidental double punctuation from "period." etc.
    text = re.sub(r"([.?!])\s*([.?!])+", r"\1", text)
    return text.strip()


def format_spoken_lists(text: str) -> str:
    """Turn dictated list speech into markdown-style lists.

    Examples:
      "bullet point clean the data bullet point validate the joins"
        -> "- Clean the data\\n- Validate the joins"
      "numbered list first check the data second verify calculations"
        -> "1. Check the data\\n2. Verify calculations"
    Returns the text unchanged when no list trigger is present.
    """
    if not text:
        return text
    lowered = text.lower()

    has_bullets = bool(_BULLET_RE.search(text))
    has_numbered = any(t in lowered for t in _NUMBERED_TRIGGERS)

    if not has_bullets and not has_numbered:
        return text

    # Strip "make this a ... list" preamble if present.
    text = _LIST_PREAMBLE_RE.sub("", text).strip()
    # A dictated "new paragraph / new line" right after the trigger is a
    # separator, not a first item — drop it before splitting.
    text = _PARA_RE.sub(" ", text)
    text = _NEWLINE_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    lowered = text.lower()
    has_bullets = bool(_BULLET_RE.search(text))
    has_numbered = any(t in lowered for t in _NUMBERED_TRIGGERS)

    if has_bullets and not has_numbered:
        parts = _BULLET_RE.split(text)
        items = [_clean_item(p) for p in parts]
        items = [i for i in items if i]
        if len(items) >= 1:
            return "\n".join(f"- {cap_first(i)}" for i in items)
        return text

    # Numbered: remove the trigger phrase, then split on ordinals.
    cleaned = text
    for trigger in _NUMBERED_TRIGGERS:
        cleaned = re.compile(re.escape(trigger), re.IGNORECASE).sub(
            " ", cleaned)
    parts = _ORDINAL_SPLIT_RE.split(cleaned)
    items = [_clean_item(p) for p in parts]
    items = [i for i in items if i]
    if len(items) >= 2:
        return "\n".join(f"{n}. {cap_first(i)}" for n, i in enumerate(items, 1))
    if len(items) == 1:
        return cap_first(items[0])
    return text


def _clean_item(item: str) -> str:
    item = item.strip(" ,.:;-").strip()
    # Remove a leading ordinal word that survived the split ("first do X").
    item = re.sub(
        r"^(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
        r"next|then|finally|lastly)\b[,:]?\s*",
        "", item, flags=re.IGNORECASE,
    ).strip(" ,.:;-").strip()
    return item


def cap_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def collapse_repeated_words(text: str) -> str:
    """Collapse STT stutter ("I I think", "the the report") — safe fix."""
    if not text:
        return text
    # Apply twice to catch triple repeats ("I I I").
    for _ in range(2):
        text = _REPEATED_WORD_RE.sub(r"\1", text)
    return text


def apply_vocabulary_casing(text: str, terms: list[str]) -> str:
    """High-confidence deterministic vocab fix: exact word-boundary match.

    Only corrects CASING ("power bi" -> "Power BI"), never replaces a
    different word with a vocab term (concept #26: don't guess on low
    confidence). Multi-word terms handled with flexible whitespace.
    """
    if not text or not terms:
        return text
    for term in terms:
        if not term or not term.strip():
            continue
        term = term.strip()
        # Build a case-insensitive whole-word pattern for the term.
        words = term.split()
        pattern = re.compile(
            r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b",
            re.IGNORECASE,
        )
        text = pattern.sub(term, text)
    return text


def normalize_transcript(raw: str, vocabulary: list[str] | None = None) -> str:
    """Full deterministic pass. Cheap, safe, always applied pre-LLM.

    Order:
      1. strip + collapse whitespace
      2. collapse repeated words (stutter)
      3. spoken-list formatting (needs words intact)
      4. spoken-punctuation interpretation
      5. vocabulary casing fix
      6. final whitespace tidy
    """
    if not raw or not raw.strip():
        return ""
    text = raw.strip()
    text = _MULTI_SPACE_RE.sub(" ", text.replace("\t", " "))
    text = collapse_repeated_words(text)
    listed = format_spoken_lists(text)
    if listed != text:
        # List path already capitalizes items; still interpret any
        # punctuation words inside items, line by line — without
        # re-interpreting structural markers (would corrupt "1." lines).
        lines = [interpret_spoken_punctuation(ln, structural=False)
                 for ln in listed.split("\n")]
        text = "\n".join(ln.strip() for ln in lines if ln.strip())
    else:
        text = interpret_spoken_punctuation(text)
    if vocabulary:
        # Apply per-line so list markers ("- ", "1. ") survive.
        lines = [apply_vocabulary_casing(ln, vocabulary) for ln in text.split("\n")]
        text = "\n".join(lines)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    text = "\n".join(
        _MULTI_SPACE_RE.sub(" ", ln).strip() for ln in text.split("\n")
    ).strip()
    return text
