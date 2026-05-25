"""Importers convert raw uploads into a normalized list of chapters.

Each importer returns: list[dict] with keys {kind, title, html}.
- kind ∈ {front_title, front_copyright, front_dedication, front_toc,
          front_acknowledgments, front_foreword, front_preface,
          body, back_about, back_alsoby, back_acknowledgments}
- title: plain text
- html:  sanitized HTML fragment (no <html>/<body> wrapper)
"""
from pathlib import Path
from . import txt as txt_mod, md as md_mod, html as html_mod, docx as docx_mod
from .common import count_words

EXT_MAP = {
    ".txt": txt_mod.import_txt,
    ".md": md_mod.import_md,
    ".markdown": md_mod.import_md,
    ".html": html_mod.import_html,
    ".htm": html_mod.import_html,
    ".docx": docx_mod.import_docx,
}


def import_file(filename: str, data: bytes) -> list[dict]:
    ext = Path(filename).suffix.lower()
    fn = EXT_MAP.get(ext)
    if fn is None:
        raise ValueError(f"Unsupported file type: {ext}")
    chapters = fn(data)
    for ch in chapters:
        ch["word_count"] = count_words(ch["html"])
    return chapters


SUPPORTED_EXTS = sorted(EXT_MAP.keys())
