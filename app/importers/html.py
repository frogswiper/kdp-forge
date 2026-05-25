"""HTML importer. Split on h1 (or h2 if no h1)."""
from bs4 import BeautifulSoup
from .common import finalize, detect_kind


def _pick_heading_level(soup: BeautifulSoup) -> str:
    for lvl in ("h1", "h2", "h3"):
        if soup.find(lvl):
            return lvl
    return "h1"


def split_by_headings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    # Drop scripts/styles
    for bad in soup(["script", "style", "noscript"]):
        bad.decompose()
    container = soup.body or soup
    level = _pick_heading_level(container)

    chapters: list[dict] = []
    current = {"title": None, "nodes": []}

    def flush():
        if current["title"] is None and not current["nodes"]:
            return
        title = current["title"] or "Prologue"
        body_html = "".join(str(n) for n in current["nodes"]).strip()
        chapters.append({"kind": detect_kind(title), "title": title, "html": body_html})

    for el in list(container.children):
        if getattr(el, "name", None) == level:
            flush()
            current = {"title": el.get_text(" ", strip=True), "nodes": []}
        else:
            current["nodes"].append(el)
    flush()
    return chapters


def import_html(data: bytes) -> list[dict]:
    text = data.decode("utf-8", errors="replace")
    chapters = split_by_headings(text)
    if not chapters:
        soup = BeautifulSoup(text, "html.parser")
        body = (soup.body or soup).decode_contents()
        return finalize([{"kind": "body", "title": "Chapter 1", "html": body}])
    return finalize(chapters)
