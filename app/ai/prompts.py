"""Prompt templates + helpers for editorial assist.

Each generator takes a Book context dict and returns a JSON-shaped result.
"""
from .client import chat_json


def _excerpt(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:
        cut = cut[:sp]
    return cut + " […]"


def _book_context(ctx: dict, body_limit: int = 4000) -> str:
    lines = []
    if ctx.get("title"):
        lines.append(f"Title: {ctx['title']}")
    if ctx.get("subtitle"):
        lines.append(f"Subtitle: {ctx['subtitle']}")
    if ctx.get("author"):
        lines.append(f"Author: {ctx['author']}")
    if ctx.get("language"):
        lines.append(f"Language: {ctx['language']}")
    if ctx.get("description"):
        lines.append(f"Existing description: {ctx['description']}")
    if ctx.get("genre_hint"):
        lines.append(f"Genre hint: {ctx['genre_hint']}")
    if ctx.get("first_chapter_text"):
        lines.append("\nFirst body chapter (excerpt):\n" + _excerpt(ctx["first_chapter_text"], body_limit))
    return "\n".join(lines)


SYS_EDITOR = (
    "You are a sharp, experienced acquisitions editor at a major trade publisher. "
    "You write copy that respects the reader and never overpromises. "
    "You always return valid JSON only — no prose, no markdown fences."
)


async def gen_blurb(ctx: dict, model: str | None = None) -> dict:
    """Generate 3 blurb candidates of varying length."""
    user = (
        "Based on the book context below, write THREE back-cover blurb candidates "
        "for the Amazon product page. Each must:\n"
        "- be in the voice of marketing copy, not a synopsis\n"
        "- avoid spoilers\n"
        "- avoid clichés ('a tour de force', 'gripping', 'unputdownable')\n"
        "- mention the protagonist's situation, the stakes, and a hint of tone\n"
        "- end on a hook line\n\n"
        f"BOOK CONTEXT:\n{_book_context(ctx)}\n"
    )
    schema = {
        "candidates": [
            {"length": "short", "chars": 200, "text": "<~200 char blurb>"},
            {"length": "medium", "chars": 500, "text": "<~500 char blurb>"},
            {"length": "long", "chars": 1200, "text": "<~1200 char blurb>"},
        ]
    }
    return await chat_json(SYS_EDITOR, user, model=model or _model(), schema_hint=schema)


async def gen_keywords(ctx: dict, model: str | None = None) -> dict:
    """Suggest 7 KDP keywords with rationale."""
    user = (
        "Suggest 7 Amazon KDP keywords for this book. KDP keywords are NOT just single words — "
        "they should be reader-search phrases (2-5 words) like 'literary fiction nordic' or "
        "'memoir-style novel about fathers'. Avoid brand names. Avoid the book title.\n\n"
        f"BOOK CONTEXT:\n{_book_context(ctx)}\n"
    )
    schema = {
        "keywords": [
            {"term": "<phrase>", "rationale": "<one-sentence why>"}
            for _ in range(7)
        ]
    }
    return await chat_json(SYS_EDITOR, user, model=model or _model(), schema_hint=schema)


async def gen_bisac(ctx: dict, model: str | None = None) -> dict:
    """Suggest BISAC categories most likely to convert + rationale."""
    user = (
        "Recommend the 5 best BISAC subject codes for this book, ranked by likely Amazon "
        "browse-category fit. Return real BISAC codes (e.g. FIC019000) with the official label "
        "and a one-line rationale.\n\n"
        f"BOOK CONTEXT:\n{_book_context(ctx)}\n"
    )
    schema = {
        "categories": [
            {"code": "FIC019000", "label": "FICTION / Literary", "why": "<short reason>"}
            for _ in range(5)
        ]
    }
    return await chat_json(SYS_EDITOR, user, model=model or _model(), schema_hint=schema)


def _model():
    from .client import DEFAULT_MODEL
    return DEFAULT_MODEL


SYS_LINE_EDITOR = (
    "You are a sharp, light-touch line editor. You preserve the author's voice. "
    "You never rewrite prose for the sake of it. You only flag changes that fix "
    "ambiguity, redundancy, awkward rhythm, or factual issues. "
    "You always return valid JSON only — no prose, no markdown fences."
)


async def gen_copyedit(chapter_text: str, book_title: str = "", model: str | None = None) -> dict:
    """Suggest specific inline edits for a chapter."""
    user = (
        "Read the chapter prose below and propose up to 12 specific line edits. "
        "For each, quote the exact original substring, propose a replacement, and "
        "give a one-line reason. Skip preferences — only flag real improvements. "
        "Be conservative: if the prose is fine, return fewer (or zero) edits.\n\n"
        + (f"BOOK: {book_title}\n" if book_title else "")
        + "CHAPTER:\n" + _excerpt(chapter_text, 8000)
    )
    schema = {
        "edits": [
            {
                "original": "<exact substring from the chapter>",
                "suggestion": "<your proposed replacement>",
                "reason": "<one line>",
                "kind": "clarity|rhythm|redundancy|factual|other",
            }
        ]
    }
    return await chat_json(SYS_LINE_EDITOR, user, model=model or _model(), schema_hint=schema, temperature=0.4)


SYS_CRITIC = (
    "You are an experienced developmental editor giving a craft critique. "
    "You are honest, specific, and free of hedging. You quote short snippets when "
    "useful. You always return valid JSON only — no prose, no markdown fences."
)


async def gen_critique(chapter_text: str, chapter_title: str = "", model: str | None = None) -> dict:
    """Structured developmental critique of a chapter."""
    user = (
        "Critique the chapter below across four lenses. For each, give a one-sentence "
        "verdict, two or three specific observations (cite short snippets), and one "
        "concrete suggestion. Then give an overall score 1-10.\n\n"
        + (f"CHAPTER TITLE: {chapter_title}\n" if chapter_title else "")
        + "CHAPTER:\n" + _excerpt(chapter_text, 8000)
    )
    schema = {
        "hook": {"verdict": "<one sentence>", "observations": ["<...>"], "suggestion": "<...>"},
        "pacing": {"verdict": "<one sentence>", "observations": ["<...>"], "suggestion": "<...>"},
        "dialogue": {"verdict": "<one sentence>", "observations": ["<...>"], "suggestion": "<...>"},
        "ending": {"verdict": "<one sentence>", "observations": ["<...>"], "suggestion": "<...>"},
        "overall_score": 7,
        "overall_summary": "<two-sentence summary>",
    }
    return await chat_json(SYS_CRITIC, user, model=model or _model(), schema_hint=schema, temperature=0.5)


async def gen_hook_check(opening_text: str, model: str | None = None) -> dict:
    """Score the opening hook and propose an alternative first line."""
    user = (
        "Evaluate the opening of this chapter as a hook. Score 1-10, list what's working, "
        "list what could be sharper, and write THREE alternative first lines that pull the "
        "reader in harder without changing the chapter's meaning or voice.\n\n"
        "OPENING:\n" + _excerpt(opening_text, 1200)
    )
    schema = {
        "score": 7,
        "working": ["<bullet>"],
        "sharper": ["<bullet>"],
        "alternative_first_lines": ["<line 1>", "<line 2>", "<line 3>"],
    }
    return await chat_json(SYS_CRITIC, user, model=model or _model(), schema_hint=schema, temperature=0.7)
