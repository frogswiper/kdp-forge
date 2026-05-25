"""Build the KDP submission bundle from a Book."""
import json
from typing import Iterable


def _parse_list(s: str | None) -> list[str]:
    if not s:
        return []
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _parse_contributors(s: str | None) -> list[dict]:
    if not s:
        return []
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [c for c in v if isinstance(c, dict)]
    except Exception:
        pass
    return []


def build_payload(book, total_words: int, chapter_count: int) -> dict:
    keywords = _parse_list(book.keywords)
    categories = _parse_list(book.categories)
    return {
        "title": book.title or "",
        "subtitle": book.subtitle or "",
        "series": {"name": book.series_name or "", "number": book.series_number or ""},
        "edition": book.edition or "",
        "author": book.author or "",
        "contributors": _parse_contributors(book.contributors),
        "language": book.language or "en",
        "description": book.description or "",
        "keywords": keywords[:7],
        "categories": categories[:3],
        "age_range": {"min": book.age_min, "max": book.age_max} if (book.age_min or book.age_max) else None,
        "adult_content": bool(book.adult_content),
        "isbn": book.isbn or "",
        "publisher": book.publisher or "Independently Published",
        "publication_date": book.pub_date or "",
        "public_domain": bool(book.public_domain),
        "stats": {"chapters": chapter_count, "words": total_words},
    }


def build_json(book, total_words: int, chapter_count: int) -> bytes:
    return json.dumps(
        build_payload(book, total_words, chapter_count),
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")


def build_markdown(book, total_words: int, chapter_count: int) -> bytes:
    p = build_payload(book, total_words, chapter_count)
    L = []
    L.append(f"# KDP submission bundle — {p['title']}")
    L.append("")
    L.append("Copy each field into the matching KDP upload form input.")
    L.append("")

    L.append("## Book details")
    L.append("")
    L.append(f"- **Language:** {p['language']}")
    L.append(f"- **Book title:** {p['title']}")
    L.append(f"- **Subtitle:** {p['subtitle'] or '_(none)_'}")
    if p['series']['name']:
        L.append(f"- **Series name:** {p['series']['name']}")
        L.append(f"- **Series number:** {p['series']['number'] or '_(none)_'}")
    if p['edition']:
        L.append(f"- **Edition number:** {p['edition']}")
    L.append(f"- **Author:** {p['author'] or '_(set author name)_'}")
    if p['contributors']:
        L.append("- **Contributors:**")
        for c in p['contributors']:
            L.append(f"  - {c.get('role','contributor')}: {c.get('name','')}")
    L.append("")

    L.append("## Description")
    L.append("")
    L.append("> KDP allows up to ~4,000 characters. Plain text or basic HTML.")
    L.append("")
    L.append(p['description'] or "_(write a description)_")
    L.append("")
    L.append(f"_({len(p['description'])} chars)_")
    L.append("")

    L.append("## Publishing rights")
    L.append("")
    if p['public_domain']:
        L.append("- This is a **public domain** work.")
    else:
        L.append("- I own the copyright and hold the necessary publishing rights.")
    L.append("")

    L.append("## Keywords (max 7)")
    L.append("")
    if p['keywords']:
        for i, k in enumerate(p['keywords'], 1):
            L.append(f"{i}. {k}")
    else:
        L.append("_(add up to 7 keywords)_")
    L.append("")

    L.append("## Categories (max 3 BISAC)")
    L.append("")
    if p['categories']:
        for i, c in enumerate(p['categories'], 1):
            L.append(f"{i}. {c}")
    else:
        L.append("_(pick up to 3 BISAC categories, e.g. FIC019000 LITERARY)_")
    L.append("")

    if p['age_range']:
        L.append("## Age & grade range")
        L.append("")
        L.append(f"- Min age: {p['age_range']['min'] or '_(unset)_'}")
        L.append(f"- Max age: {p['age_range']['max'] or '_(unset)_'}")
        L.append("")

    L.append("## Content rating")
    L.append("")
    L.append(f"- Contains adult content: **{'Yes' if p['adult_content'] else 'No'}**")
    L.append("")

    L.append("## Publication & identifiers")
    L.append("")
    L.append(f"- **Publisher:** {p['publisher']}")
    L.append(f"- **Publication date:** {p['publication_date'] or '_(let KDP assign)_'}")
    L.append(f"- **ISBN:** {p['isbn'] or '_(use the free KDP-provided ISBN)_'}")
    L.append("")

    L.append("## Book stats (for your reference)")
    L.append("")
    L.append(f"- Chapters: {p['stats']['chapters']}")
    L.append(f"- Word count: {p['stats']['words']:,}")
    L.append("")

    return "\n".join(L).encode("utf-8")
