import os
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Form, Body
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slugify import slugify
from sqlalchemy import select

from .db import Session, init_db, Book, Chapter, Snapshot
from .importers import import_file, SUPPORTED_EXTS
from .importers.common import count_words, sanitize_html
from .exporters.epub import build_epub
from .exporters.pdf import build_pdf, KDP_TRIMS
from .exporters import kdp_meta
from .ai import prompts as ai_prompts
from .ai.client import list_models as ai_list_models, DEFAULT_MODEL
from fastapi.responses import Response
from slugify import slugify as _slugify
from bs4 import BeautifulSoup

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "books").mkdir(exist_ok=True)
(DATA_DIR / "imports").mkdir(exist_ok=True)

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="kdp-forge", version="0.3.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


async def _unique_slug(session, base: str) -> str:
    base = base or "untitled"
    candidate = base
    n = 2
    while True:
        existing = await session.scalar(select(Book).where(Book.slug == candidate))
        if existing is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    async with Session() as s:
        books = (await s.scalars(select(Book).order_by(Book.created_at.desc()))).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "books": books,
        "supported": SUPPORTED_EXTS,
    })


@app.post("/books/import")
async def books_import(
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    try:
        chapters = import_file(file.filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not chapters:
        raise HTTPException(400, "No chapters detected.")

    book_title = (title or "").strip() or Path(file.filename).stem
    ext = Path(file.filename).suffix.lower().lstrip(".")

    async with Session() as s:
        slug = await _unique_slug(s, slugify(book_title))
        book = Book(
            slug=slug,
            title=book_title,
            author=(author or "").strip() or None,
            source_format=ext,
        )
        s.add(book)
        await s.flush()
        for i, ch in enumerate(chapters):
            s.add(Chapter(
                book_id=book.id,
                position=i,
                kind=ch["kind"],
                title=ch["title"],
                html=ch["html"],
                word_count=ch.get("word_count", 0),
            ))
        await s.commit()

    safe_name = slugify(Path(file.filename).stem) + Path(file.filename).suffix.lower()
    (DATA_DIR / "imports" / safe_name).write_bytes(data)

    return RedirectResponse(url=f"/books/{slug}", status_code=303)


@app.get("/books/{slug}", response_class=HTMLResponse)
async def book_view(request: Request, slug: str, ch: int | None = None):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404, "Book not found.")
        chapters = (await s.scalars(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position)
        )).all()
        snapshots = (await s.scalars(
            select(Snapshot).where(Snapshot.book_id == book.id).order_by(Snapshot.created_at.desc())
        )).all()
    current = next((c for c in chapters if c.position == ch), chapters[0] if chapters else None)
    total_words = sum(c.word_count for c in chapters)
    return templates.TemplateResponse("book.html", {
        "request": request,
        "book": book,
        "chapters": chapters,
        "current": current,
        "total_words": total_words,
        "snapshots": snapshots,
    })


def _list_to_lines(s: str | None) -> str:
    if not s:
        return ""
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return "\n".join(str(x) for x in v)
    except Exception:
        pass
    return s


def _lines_to_json(s: str | None) -> str | None:
    if s is None:
        return None
    items: list[str] = []
    for line in s.replace(",", "\n").splitlines():
        line = line.strip()
        if line:
            items.append(line)
    return json.dumps(items) if items else None


@app.get("/books/{slug}/metadata", response_class=HTMLResponse)
async def metadata_view(request: Request, slug: str, saved: int = 0):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
    return templates.TemplateResponse("metadata.html", {
        "request": request,
        "book": book,
        "saved": bool(saved),
        "keywords_text": _list_to_lines(book.keywords),
        "categories_text": _list_to_lines(book.categories),
    })


@app.post("/books/{slug}/metadata")
async def metadata_save(slug: str, request: Request):
    form = await request.form()
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)

        for col in ("title", "subtitle", "author", "language",
                    "series_name", "series_number", "edition",
                    "publisher", "pub_date", "isbn", "description"):
            v = form.get(col)
            if v is not None:
                setattr(book, col, (v.strip() or None) if col != "title" else (v.strip() or book.title))

        book.keywords = _lines_to_json(form.get("keywords"))
        book.categories = _lines_to_json(form.get("categories"))

        age_min = form.get("age_min")
        age_max = form.get("age_max")
        book.age_min = int(age_min) if age_min and age_min.strip() else None
        book.age_max = int(age_max) if age_max and age_max.strip() else None

        book.adult_content = form.get("adult_content") == "1"
        book.public_domain = form.get("public_domain") == "1"

        await s.commit()
    return RedirectResponse(url=f"/books/{slug}/metadata?saved=1", status_code=303)


@app.post("/books/{slug}/delete")
async def book_delete(slug: str):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        await s.delete(book)
        await s.commit()
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.patch("/api/chapters/{chapter_id}")
async def chapter_update(chapter_id: int, payload: dict = Body(...)):
    async with Session() as s:
        ch = await s.get(Chapter, chapter_id)
        if ch is None:
            raise HTTPException(404, "Chapter not found.")
        if "html" in payload:
            ch.html = sanitize_html(payload["html"] or "")
            ch.word_count = count_words(ch.html)
        if "title" in payload:
            ch.title = (payload["title"] or "").strip() or ch.title
        if "kind" in payload and payload["kind"]:
            ch.kind = payload["kind"]
        await s.commit()
        return {
            "id": ch.id,
            "title": ch.title,
            "kind": ch.kind,
            "word_count": ch.word_count,
            "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
        }


@app.get("/api/books/{slug}/export.epub")
async def export_epub(slug: str):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        chapters = (await s.scalars(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position)
        )).all()
    data = build_epub(book, chapters)
    filename = f"{_slugify(book.title) or book.slug}.epub"
    return Response(
        content=data,
        media_type="application/epub+zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _build_ai_context(session, book) -> dict:
    chapters = (await session.scalars(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position)
    )).all()
    body_chapters = [c for c in chapters if c.kind == "body"]
    first_body = body_chapters[0] if body_chapters else (chapters[0] if chapters else None)
    first_text = ""
    if first_body and first_body.html:
        first_text = BeautifulSoup(first_body.html, "html.parser").get_text("\n", strip=True)
    return {
        "title": book.title or "",
        "subtitle": book.subtitle or "",
        "author": book.author or "",
        "language": book.language or "en",
        "description": book.description or "",
        "first_chapter_text": first_text,
    }


@app.get("/api/ai/models")
async def ai_models():
    try:
        models = await ai_list_models()
    except Exception as e:
        raise HTTPException(503, f"Ollama unreachable: {e}")
    return {"default": DEFAULT_MODEL, "models": models}


@app.post("/api/books/{slug}/ai/blurb")
async def ai_blurb(slug: str, payload: dict = Body(default={})):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        ctx = await _build_ai_context(s, book)
    try:
        return await ai_prompts.gen_blurb(ctx, model=payload.get("model"))
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


@app.post("/api/books/{slug}/ai/keywords")
async def ai_keywords(slug: str, payload: dict = Body(default={})):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        ctx = await _build_ai_context(s, book)
    try:
        return await ai_prompts.gen_keywords(ctx, model=payload.get("model"))
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


@app.post("/api/chapters/{chapter_id}/ai/copyedit")
async def ai_copyedit(chapter_id: int, payload: dict = Body(default={})):
    async with Session() as s:
        ch = await s.get(Chapter, chapter_id)
        if ch is None:
            raise HTTPException(404)
        book = await s.get(Book, ch.book_id)
    text = BeautifulSoup(ch.html or "", "html.parser").get_text("\n", strip=True)
    if not text.strip():
        return {"edits": []}
    try:
        return await ai_prompts.gen_copyedit(text, book_title=book.title if book else "", model=payload.get("model"))
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


@app.post("/api/chapters/{chapter_id}/ai/critique")
async def ai_critique(chapter_id: int, payload: dict = Body(default={})):
    async with Session() as s:
        ch = await s.get(Chapter, chapter_id)
        if ch is None:
            raise HTTPException(404)
    text = BeautifulSoup(ch.html or "", "html.parser").get_text("\n", strip=True)
    if not text.strip():
        raise HTTPException(400, "Chapter is empty.")
    try:
        return await ai_prompts.gen_critique(text, chapter_title=ch.title or "", model=payload.get("model"))
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


@app.post("/api/chapters/{chapter_id}/ai/hook")
async def ai_hook(chapter_id: int, payload: dict = Body(default={})):
    async with Session() as s:
        ch = await s.get(Chapter, chapter_id)
        if ch is None:
            raise HTTPException(404)
    text = BeautifulSoup(ch.html or "", "html.parser").get_text("\n", strip=True)
    # First ~1200 chars covers most opening hooks
    opening = text[:1200].strip()
    if not opening:
        raise HTTPException(400, "Chapter is empty.")
    try:
        return await ai_prompts.gen_hook_check(opening, model=payload.get("model"))
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


@app.post("/api/books/{slug}/ai/bisac")
async def ai_bisac(slug: str, payload: dict = Body(default={})):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        ctx = await _build_ai_context(s, book)
    try:
        return await ai_prompts.gen_bisac(ctx, model=payload.get("model"))
    except Exception as e:
        raise HTTPException(502, f"AI error: {e}")


async def _book_stats(session, book):
    chapters = (await session.scalars(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position)
    )).all()
    return len(chapters), sum(c.word_count for c in chapters)


@app.get("/api/books/{slug}/kdp-submission.json")
async def kdp_submission_json(slug: str):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        chapter_count, total_words = await _book_stats(s, book)
    data = kdp_meta.build_json(book, total_words, chapter_count)
    filename = f"{_slugify(book.title) or book.slug}-kdp-submission.json"
    return Response(content=data, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/books/{slug}/kdp-submission.md")
async def kdp_submission_md(slug: str):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        chapter_count, total_words = await _book_stats(s, book)
    data = kdp_meta.build_markdown(book, total_words, chapter_count)
    filename = f"{_slugify(book.title) or book.slug}-kdp-submission.md"
    return Response(content=data, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/books/{slug}/export.pdf")
async def export_pdf(slug: str, trim: str = "6x9", pages: int = 200):
    if trim not in KDP_TRIMS:
        raise HTTPException(400, f"Unknown trim. Choices: {sorted(KDP_TRIMS)}")
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        chapters = (await s.scalars(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position)
        )).all()
    data = build_pdf(book, chapters, trim=trim, page_count=max(24, pages))
    filename = f"{_slugify(book.title) or book.slug}-{trim}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/books/{slug}/snapshots")
async def snapshot_create(slug: str, payload: dict = Body(default={})):
    label = (payload.get("label") or "").strip()
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        chapters = (await s.scalars(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position)
        )).all()
        blob = json.dumps([
            {"position": c.position, "kind": c.kind, "title": c.title,
             "html": c.html, "word_count": c.word_count}
            for c in chapters
        ])
        snap = Snapshot(book_id=book.id, label=label or "manual", blob=blob)
        s.add(snap)
        await s.commit()
        return {
            "id": snap.id, "label": snap.label,
            "created_at": snap.created_at.isoformat(),
            "chapter_count": len(chapters),
        }


@app.post("/api/books/{slug}/snapshots/{snap_id}/restore")
async def snapshot_restore(slug: str, snap_id: int):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        snap = await s.get(Snapshot, snap_id)
        if snap is None or snap.book_id != book.id:
            raise HTTPException(404, "Snapshot not found.")

        # Auto-snapshot current state before restoring.
        current = (await s.scalars(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.position)
        )).all()
        pre_blob = json.dumps([
            {"position": c.position, "kind": c.kind, "title": c.title,
             "html": c.html, "word_count": c.word_count}
            for c in current
        ])
        s.add(Snapshot(book_id=book.id, label=f"auto: pre-restore @ {datetime.utcnow().strftime('%H:%M')}", blob=pre_blob))

        # Wipe & rebuild chapters from snapshot.
        for c in current:
            await s.delete(c)
        await s.flush()
        data = json.loads(snap.blob)
        for entry in data:
            s.add(Chapter(
                book_id=book.id,
                position=entry["position"],
                kind=entry["kind"],
                title=entry["title"],
                html=entry["html"],
                word_count=entry.get("word_count", count_words(entry["html"])),
            ))
        await s.commit()
        return {"ok": True, "restored": len(data)}


@app.post("/api/books/{slug}/snapshots/{snap_id}/delete")
async def snapshot_delete(slug: str, snap_id: int):
    async with Session() as s:
        book = await s.scalar(select(Book).where(Book.slug == slug))
        if book is None:
            raise HTTPException(404)
        snap = await s.get(Snapshot, snap_id)
        if snap is None or snap.book_id != book.id:
            raise HTTPException(404)
        await s.delete(snap)
        await s.commit()
        return {"ok": True}


@app.get("/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "milestone": "M8",
        "data_dir": str(DATA_DIR),
        "ollama_url": os.environ.get("OLLAMA_URL"),
        "supported_imports": SUPPORTED_EXTS,
    })
