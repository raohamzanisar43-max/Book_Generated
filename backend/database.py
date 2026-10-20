"""Database engine, session handling and ORM models."""
import uuid
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from backend.config import settings  # re-exported for backwards compatibility

_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    # Columns are timezone-naive; store UTC consistently.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Book(Base):
    __tablename__ = "books"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    notes_on_outline_before = Column(Text)
    outline_status = Column(String, default="pending")
    final_review_notes_status = Column(String, default="no")
    book_output_status = Column(String, default="in_progress")
    target_chapters = Column(Integer)
    pages_per_chapter = Column(Integer)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    outlines = relationship(
        "Outline", back_populates="book", cascade="all, delete-orphan", order_by="Outline.created_at"
    )
    chapters = relationship(
        "Chapter", back_populates="book", cascade="all, delete-orphan", order_by="Chapter.chapter_number"
    )
    logs = relationship("Log", back_populates="book", cascade="all, delete-orphan", order_by="Log.created_at")


class Outline(Base):
    __tablename__ = "outlines"

    id = Column(String, primary_key=True, default=_uuid)
    book_id = Column(String, ForeignKey("books.id"), nullable=False)
    content = Column(Text)
    notes_on_outline_after = Column(Text)
    status = Column(String, default="review_needed")
    created_at = Column(DateTime, default=_utcnow)

    book = relationship("Book", back_populates="outlines")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(String, primary_key=True, default=_uuid)
    book_id = Column(String, ForeignKey("books.id"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String)
    content = Column(Text)
    summary = Column(Text)
    chapter_notes_status = Column(String, default="no")
    chapter_notes = Column(Text)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=_utcnow)

    book = relationship("Book", back_populates="chapters")


class Log(Base):
    __tablename__ = "logs"

    id = Column(String, primary_key=True, default=_uuid)
    book_id = Column(String, ForeignKey("books.id"))
    message = Column(Text)
    level = Column(String)
    created_at = Column(DateTime, default=_utcnow)

    book = relationship("Book", back_populates="logs")


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added after the initial release: (table, column, SQL type).
_ADDED_COLUMNS = [
    ("books", "target_chapters", "INTEGER"),
    ("books", "pages_per_chapter", "INTEGER"),
]


def create_tables() -> None:
    """Create missing tables and add columns introduced in later versions (idempotent)."""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, column, sql_type in _ADDED_COLUMNS:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
