"""Shared helpers used by all importers."""
import re
import bleach
from bs4 import BeautifulSoup

ALLOWED_TAGS = [
    "p", "br", "em", "i", "strong", "b", "u",
    "blockquote", "hr",
    "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "code", "pre",
]
ALLOWED_ATTRS = {"a": ["href", "title"]}

FRONT_KINDS = {
    "title page": "front_title",
    "title": "front_title",
    "copyright": "front_copyright",
    "dedication": "front_dedication",
    "table of contents": "front_toc",
    "contents": "front_toc",
    "toc": "front_toc",
    "acknowledgments": "front_acknowledgments",
    "acknowledgements": "front_acknowledgments",
    "foreword": "front_foreword",
    "preface": "front_preface",
    "introduction": "front_preface",
    "prologue": "body",
    "epilogue": "body",
}
BACK_KINDS = {
    "about the author": "back_about",
    "also by": "back_alsoby",
    "afterword": "back_about",
}

CHAPTER_HEAD_RE = re.compile(
    r"^\s*(chapter\s+\d+|chapter\s+[ivxlcdm]+|\d+\.\s|[ivxlcdm]+\.\s)",
    re.IGNORECASE,
)


def sanitize_html(s: str) -> str:
    return bleach.clean(s, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def count_words(html: str) -> int:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return len([w for w in re.split(r"\s+", text) if w])


def detect_kind(title: str, position_hint: str = "auto") -> str:
    """Map a chapter title to a kind. position_hint: 'front' | 'back' | 'auto'."""
    t = (title or "").strip().lower()
    if not t:
        return "body"
    if t in FRONT_KINDS:
        return FRONT_KINDS[t]
    if t in BACK_KINDS:
        return BACK_KINDS[t]
    for key, kind in FRONT_KINDS.items():
        if t.startswith(key):
            return kind
    for key, kind in BACK_KINDS.items():
        if t.startswith(key):
            return kind
    return "body"


def looks_like_chapter_heading(line: str) -> bool:
    return bool(CHAPTER_HEAD_RE.match(line or ""))


def looks_like_named_section(line: str) -> bool:
    """True if the line is exactly a known front/back-matter section name."""
    t = (line or "").strip().rstrip(":").lower()
    if not t or len(t) > 40:
        return False
    return t in FRONT_KINDS or t in BACK_KINDS


def reclassify_back_matter(chapters: list[dict]) -> list[dict]:
    """Any back-matter-named chapter after the first body chapter gets back_* kind."""
    seen_body = False
    out = []
    for ch in chapters:
        title_l = (ch["title"] or "").strip().lower()
        if seen_body and title_l in BACK_KINDS:
            ch = {**ch, "kind": BACK_KINDS[title_l]}
        if ch["kind"] == "body":
            seen_body = True
        out.append(ch)
    return out


def finalize(chapters: list[dict]) -> list[dict]:
    """Sanitize HTML, drop empty chapters, run back-matter pass."""
    cleaned = []
    for ch in chapters:
        html = sanitize_html(ch.get("html", "")).strip()
        title = (ch.get("title") or "").strip() or "Untitled"
        if not html and ch.get("kind", "body") == "body":
            continue
        cleaned.append({"kind": ch.get("kind") or detect_kind(title), "title": title, "html": html})
    return reclassify_back_matter(cleaned)
