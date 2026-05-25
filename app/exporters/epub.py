"""EPUB 3 export.

Spine ordering: front matter (in import order, excluding TOC which is generated
by the reader) → body chapters → back matter.
"""
import io
import uuid
from typing import Iterable

from ebooklib import epub


FRONT_KINDS = {
    "front_title", "front_copyright", "front_dedication",
    "front_acknowledgments", "front_foreword", "front_preface",
}
BACK_KINDS = {"back_about", "back_alsoby", "back_acknowledgments"}

STYLESHEET = """
@namespace epub "http://www.idpf.org/2007/ops";
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.6; margin: 0 1.2em; }
h1.chapter-title { text-align: center; margin: 2em 0 1.5em; font-weight: normal; font-size: 1.6em; }
h1.chapter-kind { display: none; }
p.chapter-kind { text-align: center; text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75em; margin: 3em 0 0.5em; }
p { margin: 0 0 0.9em; text-align: justify; text-indent: 1.2em; }
p.first, p:first-of-type { text-indent: 0; }
blockquote { margin: 1em 2em; font-style: italic; }
hr { border: none; text-align: center; margin: 1.5em 0; }
hr::after { content: "* * *"; letter-spacing: 0.4em; }
h2 { font-size: 1.2em; margin: 1.5em 0 0.6em; }
h3 { font-size: 1.05em; margin: 1.2em 0 0.5em; }
"""


def _chapter_kind_label(kind: str) -> str:
    return kind.replace("front_", "").replace("back_", "").replace("_", " ")


def _sort_for_spine(chapters: list) -> list:
    """Stable sort: front (in position order) → body → back."""
    front = [c for c in chapters if c.kind in FRONT_KINDS]
    body = [c for c in chapters if c.kind == "body"]
    back = [c for c in chapters if c.kind in BACK_KINDS]
    return front + body + back


def _xhtml_body(c, kind_label: str) -> str:
    safe_title = (c.title or "").replace("<", "&lt;").replace(">", "&gt;")
    parts = [f'<p class="chapter-kind">{kind_label}</p>'] if c.kind != "body" else []
    parts.append(f'<h1 class="chapter-title">{safe_title}</h1>')
    parts.append(c.html or "")
    return "\n".join(parts)


def build_epub(book, chapters: Iterable) -> bytes:
    """chapters: list of Chapter ORM rows; book: Book ORM row. Returns bytes of the .epub."""
    eb = epub.EpubBook()
    eb.set_identifier(f"urn:uuid:{uuid.uuid4()}")
    eb.set_title(book.title or "Untitled")
    eb.set_language(book.language or "en")
    if book.author:
        eb.add_author(book.author)
    if book.subtitle:
        eb.add_metadata("DC", "description", book.subtitle)

    css = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=STYLESHEET,
    )
    eb.add_item(css)

    ordered = _sort_for_spine(list(chapters))
    epub_chapters = []
    for i, c in enumerate(ordered):
        kind_label = _chapter_kind_label(c.kind)
        file_name = f"chap-{i:03d}.xhtml"
        ec = epub.EpubHtml(
            title=c.title or kind_label.title() or f"Chapter {i+1}",
            file_name=file_name,
            lang=book.language or "en",
        )
        ec.content = _xhtml_body(c, kind_label)
        ec.add_item(css)
        eb.add_item(ec)
        epub_chapters.append(ec)

    # Navigation: include body + back matter in the visible TOC, drop the
    # 'table of contents' chapter itself (the reader provides one).
    nav_items = []
    for c, ec in zip(ordered, epub_chapters):
        if c.kind == "front_toc":
            continue
        nav_items.append(ec)
    eb.toc = tuple(nav_items)

    eb.add_item(epub.EpubNcx())
    eb.add_item(epub.EpubNav())

    eb.spine = ["nav"] + epub_chapters

    buf = io.BytesIO()
    epub.write_epub(buf, eb, {})
    return buf.getvalue()
