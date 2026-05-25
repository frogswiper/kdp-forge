"""Plain text importer. Detect chapters by heading patterns or triple newlines."""
import re
from .common import looks_like_chapter_heading, looks_like_named_section, detect_kind, finalize


def _paragraphs_to_html(paras: list[str]) -> str:
    out = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        # Preserve hard line breaks inside paragraphs as <br>.
        lines = p.split("\n")
        out.append("<p>" + "<br>".join(l.strip() for l in lines if l.strip()) + "</p>")
    return "\n".join(out)


def import_txt(data: bytes) -> list[dict]:
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    # Normalize: split into paragraphs by blank line(s).
    blocks = re.split(r"\n{2,}", text)

    chapters: list[dict] = []
    current_title: str | None = None
    current_paras: list[str] = []

    def flush():
        if current_title is None and not current_paras:
            return
        title = current_title if current_title is not None else "Prologue"
        chapters.append({
            "kind": detect_kind(title),
            "title": title,
            "html": _paragraphs_to_html(current_paras),
        })

    for block in blocks:
        block = block.strip("\n")
        if not block:
            continue
        first_line = block.split("\n", 1)[0].strip()
        single_line_block = "\n" not in block
        is_heading = (
            looks_like_chapter_heading(first_line)
            or looks_like_named_section(first_line)
            or (single_line_block and len(first_line) < 80 and first_line.isupper())
        )
        if is_heading:
            flush()
            current_title = first_line
            current_paras = []
            rest = block.split("\n", 1)
            if len(rest) > 1 and rest[1].strip():
                current_paras.append(rest[1])
        else:
            current_paras.append(block)
    flush()

    if not chapters:
        chapters = [{"kind": "body", "title": "Chapter 1", "html": _paragraphs_to_html(blocks)}]
    return finalize(chapters)
