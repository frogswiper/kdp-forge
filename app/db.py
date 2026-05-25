import os
from pathlib import Path
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, UniqueConstraint, Boolean, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_URL = f"sqlite+aiosqlite:///{DATA_DIR}/kdp-forge.db"

engine = create_async_engine(DB_URL, echo=False, future=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_fk_on(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "book"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    subtitle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_format: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # KDP submission metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    categories: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    contributors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of {role,name}
    series_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    series_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    edition: Mapped[str | None] = mapped_column(String(60), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pub_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ISO date or "unset"
    isbn: Mapped[str | None] = mapped_column(String(40), nullable=True)
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adult_content: Mapped[bool] = mapped_column(Boolean, default=False)
    public_domain: Mapped[bool] = mapped_column(Boolean, default=False)

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book", cascade="all, delete-orphan",
        order_by="Chapter.position",
    )


class Chapter(Base):
    __tablename__ = "chapter"
    __table_args__ = (UniqueConstraint("book_id", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), default="body")
    title: Mapped[str] = mapped_column(String(300))
    html: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    book: Mapped["Book"] = relationship(back_populates="chapters")


class Snapshot(Base):
    __tablename__ = "snapshot"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    label: Mapped[str] = mapped_column(String(200), default="")
    blob: Mapped[str] = mapped_column(Text)  # JSON: [{position, kind, title, html, word_count}, ...]


_BOOK_ADDS = [
    ("description", "TEXT"),
    ("keywords", "TEXT"),
    ("categories", "TEXT"),
    ("contributors", "TEXT"),
    ("series_name", "VARCHAR(300)"),
    ("series_number", "VARCHAR(20)"),
    ("edition", "VARCHAR(60)"),
    ("publisher", "VARCHAR(200)"),
    ("pub_date", "VARCHAR(20)"),
    ("isbn", "VARCHAR(40)"),
    ("age_min", "INTEGER"),
    ("age_max", "INTEGER"),
    ("adult_content", "BOOLEAN DEFAULT 0"),
    ("public_domain", "BOOLEAN DEFAULT 0"),
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migration: add columns that may not exist on older DBs.
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE chapter ADD COLUMN updated_at DATETIME"
            )
        except Exception:
            pass
        for col, ddl in _BOOK_ADDS:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE book ADD COLUMN {col} {ddl}")
            except Exception:
                pass
