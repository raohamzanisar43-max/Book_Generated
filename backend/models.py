"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import settings
from backend.constants import NotesStatus, NotesStatusValue


class BookCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300, examples=["The Future of AI Automation"])
    notes_on_outline_before: str = Field(
        ...,
        min_length=1,
        description="Editor notes that guide the initial outline. Required before an outline is generated.",
        examples=["Focus on FastAPI, n8n and agentic workflows. Include practical examples."],
    )
    target_chapters: int = Field(settings.DEFAULT_CHAPTERS, ge=1, le=40, description="Number of chapters to plan.")
    pages_per_chapter: int = Field(
        settings.DEFAULT_PAGES_PER_CHAPTER, ge=1, le=40, description="Target length of each chapter in pages."
    )

    @model_validator(mode="after")
    def _strip(self):
        self.title = self.title.strip()
        self.notes_on_outline_before = self.notes_on_outline_before.strip()
        if not self.title:
            raise ValueError("title must not be blank")
        if not self.notes_on_outline_before:
            raise ValueError("notes_on_outline_before is required before generating an outline")
        return self


class FeedbackRequest(BaseModel):
    status: NotesStatusValue = Field(
        ...,
        description="`yes` = notes provided (regenerate / pause), `no` = undecided, `no_notes_needed` = approve.",
    )
    notes: str = Field("", description="Editor notes. Required when status is `yes`.")

    @model_validator(mode="after")
    def _notes_required_for_yes(self):
        self.notes = (self.notes or "").strip()
        if self.status == NotesStatus.YES and not self.notes:
            raise ValueError("notes are required when status is 'yes'")
        return self


class MessageResponse(BaseModel):
    message: str


class OutlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content: Optional[str] = None
    notes_on_outline_after: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None


class ChapterSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chapter_number: int
    title: Optional[str] = None
    status: Optional[str] = None
    chapter_notes_status: Optional[str] = None
    created_at: Optional[datetime] = None
    word_count: int = 0
    estimated_pages: float = 0
    progress: Optional[dict[str, Any]] = None


class ChapterOut(ChapterSummaryOut):
    content: Optional[str] = None
    summary: Optional[str] = None
    chapter_notes: Optional[str] = None


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    message: Optional[str] = None
    level: Optional[str] = None
    created_at: Optional[datetime] = None


class BookSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    outline_status: Optional[str] = None
    final_review_notes_status: Optional[str] = None
    book_output_status: Optional[str] = None
    chapters_written: int = 0
    chapters_planned: Optional[int] = None
    target_chapters: Optional[int] = None
    pages_per_chapter: Optional[int] = None
    total_words: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BookOut(BookSummaryOut):
    notes_on_outline_before: Optional[str] = None
    outlines: list[OutlineOut] = []
    chapters: list[ChapterSummaryOut] = []
    next_action: str = ""


class CompileResponse(BaseModel):
    message: str
    file_name: str
    file_path: str
    download_url: str
