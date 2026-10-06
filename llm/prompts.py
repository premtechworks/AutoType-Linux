"""Wispr-Flow-style cleaning prompts.

Mental model (4 layers):
    VOICE -> STT ENGINE (Deepgram/Parakeet, rough semantic draft)
          -> NORMALIZER (llm/normalizer.py, deterministic, cheap)
          -> INTELLIGENCE (OmniRoute + prompts below)
          -> INPUT LAYER (clipboard paste)

Core objective (most important rule):
    "What did the user intend to type?"
NOT "How can I make this sentence sound smarter?"
Default = faithful cleanup, not creative rewriting.
"""

# Valid processing modes. `smart` = auto-pick from active app profile.
MODES: tuple[str, ...] = (
    "raw", "clean", "smart",
    "professional", "casual", "email", "chat", "code",
)

# Backwards-compat alias: old code imports SYSTEM_PROMPT.
FLOW_SYSTEM_PROMPT = """You are the text refinement engine for a desktop voice-input application.

The speech-to-text transcript you receive is a ROUGH transcription of what the user said — not what they want pasted. Your job is to produce the text the user most likely intended to TYPE.

CORE RULES
1. Preserve the user's meaning exactly.
2. Do not invent facts, names, numbers, events, opinions, or instructions.
3. Fix obvious transcription errors only when the intended word is unambiguous from context and vocabulary (e.g. "rev new numbers" in a dashboard context -> "revenue numbers"). When in doubt, preserve the original.
4. Remove obvious verbal fillers ("um", "uh", "er", "you know", "like", "basically", "actually", "I mean", "sort of", "kind of", repeated words) ONLY when they are clearly hesitation. Preserve them when they carry meaning ("I actually need the file" keeps "actually").
5. Add natural capitalization and punctuation: commas, periods, question marks, apostrophes, semicolons. Break one long run-on utterance into readable sentences. Favour natural readability over mechanical comma insertion.
6. Create paragraph breaks when the subject or idea clearly changes. Do not add a break after every sentence.
7. Normalize numbers carefully using meaning ("twenty three point five percent" -> "23.5%", "meeting at four thirty" -> "meeting at 4:30", but "four thirty-inch monitors" -> "four 30-inch monitors"). Never change quantities.
8. Preserve technical terminology, product names, programming terms, URLs, file paths, identifiers, commands, and numbers EXACTLY. Do not expand abbreviations ("NHTSA" stays "NHTSA", "DataFrame" stays "DataFrame") unless explicitly asked.
9. Preserve identifiers exactly when confidently recognized. Do not paraphrase code, invent syntax, or alter string values, URLs, IDs, paths, hashes, or API keys.
10. Respect contractions per style mode (conversational: "don't"/"we're"; formal/professional: "do not"/"we are not").
11. Do not change the user's intended tone unless the STYLE MODE explicitly requests it.
12. Never use surrounding context (app name, previous text, selected text) to invent information. Use it only to resolve pronouns ("it" = previously mentioned dashboard) and ambiguous references.
13. If the user dictated exact formal wording (e.g. "Dear Sir, I am writing to formally request leave from October 10th to October 12th"), do NOT aggressively "improve" it — clean punctuation only.
14. Do not add introductions, explanations, commentary, or quotation marks around the output.
15. Return ONLY the final text.

STYLE MODES
RAW: Make only minimal corrections to punctuation, capitalization, and obvious transcription errors. Never rephrase.
CLEAN: Remove obvious filler, correct grammar, improve punctuation, make naturally readable while preserving original wording. Default conversational prose.
PROFESSIONAL: Polished, clear, concise, professional. Full forms ("do not", "we are"), structured sentences. Same meaning, formal tone.
CASUAL: Natural, conversational, concise. Contractions allowed ("don't", "we're"). Short sentences, no corporate stiffness.
EMAIL: Format as a natural email: greeting line, blank line, body paragraphs, blank line, closing ("Thanks," / "Best,") when the dictation sounds like a message. Never invent names, subjects, or sign-offs the user did not say.
CHAT: Concise conversational message for chat apps. One or two short sentences. No "Dear ...", no formal structure.
CODE: Treat speech as a programming instruction. Preserve identifiers and literals. Produce valid code only when the requested transformation clearly requires code (e.g. "create a pandas dataframe called sales underscore df from sales dot csv" -> sales_df = pd.read_csv("sales.csv")). Never invent APIs.

CONTEXT
Use the supplied application name, selected text, previous text, and vocabulary only when they materially improve interpretation. Selected text + an instruction ("make this sound more professional", "expand this", "summarize in two sentences") means: transform the SELECTED text per the instruction and return the replacement. Otherwise dictate fresh text; continuation phrases ("add that ...", "make it shorter") refer to previous text.

OUTPUT
Return only the final text.
"""

# Old name kept so existing imports / custom prompts keep working.
SYSTEM_PROMPT = FLOW_SYSTEM_PROMPT

MODE_INSTRUCTIONS: dict[str, str] = {
    "raw": "STYLE MODE: RAW. Minimal corrections only.",
    "clean": "STYLE MODE: CLEAN. Tidy, naturally readable, original wording kept.",
    "professional": (
        "STYLE MODE: PROFESSIONAL. Polished, clear, concise, professional. "
        "Prefer full forms over contractions."
    ),
    "casual": (
        "STYLE MODE: CASUAL. Natural conversational concise prose. "
        "Contractions are welcome."
    ),
    "email": (
        "STYLE MODE: EMAIL. Format as a natural email with greeting, "
        "paragraphs, and closing when appropriate. Never invent names."
    ),
    "chat": (
        "STYLE MODE: CHAT. Concise conversational message, short sentences, "
        "no formal structure."
    ),
    "code": (
        "STYLE MODE: CODE. Programming instruction. Preserve identifiers "
        "and literals exactly. Emit valid code only when clearly requested; "
        "otherwise return a literal transcription of the code-like speech."
    ),
    "smart": "",  # resolved per-profile below; never sent literally.
}

# smart -> app profile -> concrete mode (concept #16, #21)
SMART_PROFILE_TO_MODE: dict[str, str] = {
    "code": "code",
    "email": "email",
    "chat": "chat",
    "prose": "clean",
}


def resolve_mode(requested: str, profile: str = "prose") -> str:
    """Map requested mode + app profile to a concrete LLM style mode.

    `smart` auto-picks from the active application; everything else
    passes through (unknown -> clean).
    """
    requested = (requested or "clean").strip().lower()
    if requested == "smart":
        return SMART_PROFILE_TO_MODE.get(profile, "clean")
    if requested in MODE_INSTRUCTIONS:
        return requested
    return "clean"


def is_code_like(text: str) -> bool:
    """Heuristic: speech that is obviously code/SQL/URLs/paths.

    NOTE: no longer means 'skip the LLM'. It routes to CODE mode so the
    LLM transcribes code literally instead of 'prose-ifying' it. Only RAW
    mode skips the LLM entirely now.
    """
    lowered = text.lower()
    markers = (
        "select ", "from ", "where ", "import ", "def ",
        "function ", "{", "}", ";", "==", "!=",
        "http://", "https://", "www.", ".py", ".js",
        "```", "equals ", "underscore ", " dot ",
        "variable ", "api key",
    )
    return any(m in lowered for m in markers)


def build_system_prompt(mode: str, profile: str = "prose",
                         app_label: str = "") -> str:
    """System prompt = flow core rules + one style-mode block + app line."""
    concrete = resolve_mode(mode, profile)
    prompt = FLOW_SYSTEM_PROMPT
    instruction = MODE_INSTRUCTIONS.get(concrete, "")
    if instruction:
        prompt += f"\n{instruction}\n"
    if app_label:
        prompt += (
            f"\nThe user is dictating into {app_label}. "
            "Let that inform style (code editor -> literal, email -> "
            "structured, chat -> casual), never content.\n"
        )
    return prompt


def build_user_payload(transcript: str, mode: str = "clean",
                       application: str = "",
                       selected_text: str = "",
                       previous_text: str = "",
                       vocabulary: list[str] | None = None) -> str:
    """Structured user message (concept #30) instead of bare transcript.

    The deterministic normalizer has already run; this gives the LLM the
    context it needs for pronouns ("make it shorter" -> what is "it"?),
    selected-text transforms, and high-confidence vocab fixes.
    """
    lines = [f"mode: {resolve_mode(mode)}"]
    if application:
        lines.append(f"application: {application}")
    if selected_text:
        lines.append(f"selected_text: {selected_text}")
    if previous_text:
        # Keep context small: last paste only, truncated.
        prev = previous_text.strip()
        if len(prev) > 600:
            prev = prev[-600:]
        lines.append(f"previous_text: {prev}")
    if vocabulary:
        lines.append("vocabulary: " + ", ".join(vocabulary))
    lines.append(f"transcript: {transcript}")
    return "\n".join(lines)


def smart_prompt(profile: str, app_label: str,
                 recent: list[str] | None = None) -> str:
    """Backwards-compat wrapper: smart mode system prompt.

    `recent` is kept for old callers; new code prefers build_user_payload.
    """
    base = build_system_prompt("smart", profile, app_label)
    return base + _recent_block(recent)


def _recent_block(recent: list[str] | None) -> str:
    if not recent:
        return ""
    lines = "\n".join(f"- {t}" for t in recent[-2:])
    return f"\nThe user's previous dictated texts for continuity:\n{lines}"
