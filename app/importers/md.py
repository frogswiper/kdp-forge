"""Markdown importer using markdown-it-py."""
from markdown_it import MarkdownIt
from .html import split_by_headings
from .common import finalize

_md = MarkdownIt("commonmark", {"breaks": False, "html": False}).enable("table")


def import_md(data: bytes) -> list[dict]:
    text = data.decode("utf-8", errors="replace")
    html = _md.render(text)
    chapters = split_by_headings(html)
    if not chapters:
        return finalize([{"kind": "body", "title": "Chapter 1", "html": html}])
    return finalize(chapters)
