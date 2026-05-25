"""DOCX importer using python-docx. Split on Heading 1 (or Heading 2 if no H1)."""
import io
from docx import Document
from .common import finalize, detect_kind


def _para_to_html(p) -> str:
    parts = []
    for run in p.runs:
        text = (run.text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if not text:
            continue
        if run.bold and run.italic:
            text = f"<strong><em>{text}</em></strong>"
        elif run.bold:
            text = f"<strong>{text}</strong>"
        elif run.italic:
            text = f"<em>{text}</em>"
        parts.append(text)
    inner = "".join(parts)
    style = (p.style.name or "").lower()
    if style.startswith("heading "):
        return ""  # headings consumed as chapter titles
    if style == "blockquote":
        return f"<blockquote>{inner}</blockquote>"
    if not inner.strip():
        return ""
    return f"<p>{inner}</p>"


def _heading_level(p) -> int | None:
    name = (p.style.name or "").lower()
    if name.startswith("heading "):
        try:
            return int(name.split()[1])
        except (IndexError, ValueError):
            return None
    return None


def import_docx(data: bytes) -> list[dict]:
    doc = Document(io.BytesIO(data))
    paragraphs = list(doc.paragraphs)

    levels_present = {lvl for lvl in (_heading_level(p) for p in paragraphs) if lvl}
    split_level = 1 if 1 in levels_present else (2 if 2 in levels_present else None)

    chapters: list[dict] = []
    current_title: str | None = None
    current_html_parts: list[str] = []

    def flush():
        title = current_title or "Prologue"
        body = "\n".join(current_html_parts).strip()
        if not body and not current_title:
            return
        chapters.append({"kind": detect_kind(title), "title": title, "html": body})

    for p in paragraphs:
        lvl = _heading_level(p)
        text = p.text.strip()
        if split_level is not None and lvl == split_level and text:
            flush()
            current_title = text
            current_html_parts = []
            continue
        if lvl is not None and lvl > (split_level or 99):
            # Sub-heading: render as h2
            current_html_parts.append(f"<h2>{text}</h2>")
            continue
        rendered = _para_to_html(p)
        if rendered:
            current_html_parts.append(rendered)
    flush()

    if not chapters:
        chapters = [{
            "kind": "body",
            "title": "Chapter 1",
            "html": "\n".join(_para_to_html(p) for p in paragraphs if _para_to_html(p)),
        }]
    return finalize(chapters)
