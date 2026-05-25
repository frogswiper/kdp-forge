"""Print-ready PDF export for Amazon KDP.

KDP trim sizes + per-page-count gutter requirements baked in.
Uses CSS Paged Media (WeasyPrint).
"""
from weasyprint import HTML, CSS

# (width_in, height_in)
KDP_TRIMS: dict[str, tuple[float, float]] = {
    "5x8": (5.0, 8.0),
    "5.06x7.81": (5.06, 7.81),
    "5.25x8": (5.25, 8.0),
    "5.5x8.5": (5.5, 8.5),
    "6x9": (6.0, 9.0),
    "6.14x9.21": (6.14, 9.21),
    "6.69x9.61": (6.69, 9.61),
    "7x10": (7.0, 10.0),
    "7.44x9.69": (7.44, 9.69),
    "7.5x9.25": (7.5, 9.25),
    "8x10": (8.0, 10.0),
    "8.5x8.5": (8.5, 8.5),
    "8.5x11": (8.5, 11.0),
}

# KDP inside-margin (gutter) minimums by page count, in inches.
GUTTER_TABLE: list[tuple[int, float]] = [
    (150, 0.375),
    (300, 0.500),
    (500, 0.625),
    (700, 0.750),
    (828, 0.875),
]
DEFAULT_OUTSIDE_MARGIN = 0.5  # inches — KDP minimum is 0.25; 0.5 reads better
DEFAULT_TOP_MARGIN = 0.75
DEFAULT_BOTTOM_MARGIN = 0.75

FRONT_KINDS = {
    "front_title", "front_copyright", "front_dedication",
    "front_acknowledgments", "front_foreword", "front_preface",
}
BACK_KINDS = {"back_about", "back_alsoby", "back_acknowledgments"}


def gutter_for(page_count: int) -> float:
    for cutoff, g in GUTTER_TABLE:
        if page_count <= cutoff:
            return g
    return GUTTER_TABLE[-1][1]


def _kind_label(kind: str) -> str:
    return kind.replace("front_", "").replace("back_", "").replace("_", " ").title()


def _sort_for_spine(chapters: list) -> list:
    front = [c for c in chapters if c.kind in FRONT_KINDS]
    body = [c for c in chapters if c.kind == "body"]
    back = [c for c in chapters if c.kind in BACK_KINDS]
    return front + body + back


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chapter_html(c, idx: int, is_first_body: bool) -> str:
    cls = f"ch kind-{c.kind}"
    if is_first_body:
        cls += " first-body"
    section_attrs = f'class="{cls}" data-kind="{c.kind}"'
    if c.kind == "body":
        body_label = ""
    else:
        body_label = f'<p class="kind-label">{_escape(_kind_label(c.kind))}</p>'
    return (
        f'<section {section_attrs}>'
        f'{body_label}'
        f'<h1 class="ch-title">{_escape(c.title)}</h1>'
        f'<div class="ch-body">{c.html or ""}</div>'
        f'</section>'
    )


def _build_css(trim: str, page_count: int) -> str:
    w, h = KDP_TRIMS[trim]
    gutter = gutter_for(page_count)
    outside = DEFAULT_OUTSIDE_MARGIN
    top = DEFAULT_TOP_MARGIN
    bottom = DEFAULT_BOTTOM_MARGIN
    return f"""
@page {{
  size: {w}in {h}in;
  margin-top: {top}in;
  margin-bottom: {bottom}in;
  @bottom-center {{
    content: counter(page);
    font-family: serif;
    font-size: 9pt;
    color: #333;
  }}
}}
@page :left {{
  margin-left: {outside}in;
  margin-right: {gutter}in;
  @top-left {{
    content: string(book-title);
    font-family: serif;
    font-size: 9pt;
    font-style: italic;
    color: #555;
  }}
}}
@page :right {{
  margin-left: {gutter}in;
  margin-right: {outside}in;
  @top-right {{
    content: string(chapter-title);
    font-family: serif;
    font-size: 9pt;
    font-style: italic;
    color: #555;
  }}
}}
@page front {{
  @top-left {{ content: ""; }}
  @top-right {{ content: ""; }}
  @bottom-center {{ content: ""; }}
}}
@page chapter-opener {{
  @top-left {{ content: ""; }}
  @top-right {{ content: ""; }}
}}

.book-title-src {{ string-set: book-title content(); position: absolute; left: -10000px; top: -10000px; visibility: hidden; }}

html, body {{ font-family: "Liberation Serif", "Times New Roman", serif; font-size: 11pt; color: #000; }}
body {{ margin: 0; }}

section.ch {{
  page-break-before: right;
  page: chapter-opener;
}}
section.ch.first-body {{
  counter-reset: page 0;
}}
section.ch.kind-front_title,
section.ch.kind-front_copyright,
section.ch.kind-front_dedication,
section.ch.kind-front_acknowledgments,
section.ch.kind-front_foreword,
section.ch.kind-front_preface {{
  page: front;
}}
section.ch.kind-front_copyright {{ page-break-before: left; }}

.kind-label {{
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 9pt;
  margin: 0 0 1.5em;
  color: #444;
}}
h1.ch-title {{
  text-align: center;
  font-weight: normal;
  font-size: 18pt;
  margin: 1.5in 0 1in;
  string-set: chapter-title content();
}}
section.ch .ch-body p {{
  margin: 0;
  text-align: justify;
  text-indent: 1.2em;
  line-height: 1.45;
  hyphens: auto;
}}
section.ch .ch-body > p:first-child {{ text-indent: 0; }}
section.ch .ch-body blockquote {{
  margin: 1em 1em;
  font-style: italic;
}}
section.ch .ch-body h2 {{
  font-size: 13pt;
  margin: 1.2em 0 0.5em;
}}
section.ch .ch-body h3 {{
  font-size: 11.5pt;
  margin: 1em 0 0.4em;
}}
section.ch .ch-body hr {{
  border: none;
  text-align: center;
  margin: 1.2em 0;
}}
section.ch .ch-body hr::after {{
  content: "* * *";
  letter-spacing: 0.6em;
  color: #555;
}}

/* Front matter typesetting */
section.kind-front_title h1.ch-title {{ font-size: 24pt; margin-top: 2.5in; }}
section.kind-front_title .ch-body p {{ text-align: center; text-indent: 0; font-style: italic; }}
section.kind-front_copyright .ch-body p {{ font-size: 9pt; text-indent: 0; text-align: left; }}
section.kind-front_dedication .ch-body p {{ text-align: center; text-indent: 0; font-style: italic; margin-top: 30%; }}
section.kind-front_dedication h1.ch-title {{ display: none; }}
"""


def build_pdf(book, chapters: list, trim: str = "6x9", page_count: int = 200) -> bytes:
    if trim not in KDP_TRIMS:
        raise ValueError(f"Unknown trim: {trim}. Choices: {sorted(KDP_TRIMS)}")
    ordered = _sort_for_spine(list(chapters))

    body_parts = [
        f'<span class="book-title-src">{_escape(book.title)}</span>',
    ]
    first_body_seen = False
    for i, c in enumerate(ordered):
        is_first = (c.kind == "body" and not first_body_seen)
        if is_first:
            first_body_seen = True
        body_parts.append(_chapter_html(c, i, is_first))

    html_doc = (
        '<!doctype html><html lang="' + (book.language or "en") + '"><head>'
        '<meta charset="utf-8">'
        f'<title>{_escape(book.title)}</title>'
        '</head><body>' + "\n".join(body_parts) + "</body></html>"
    )

    css = CSS(string=_build_css(trim, page_count))
    return HTML(string=html_doc).write_pdf(stylesheets=[css])
