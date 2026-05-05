from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class BookBase(BaseModel):
    title: str
    notes_on_outline_before: str

class BookCreate(BookBase):
    pass

class Book(BookBase):
    id: UUID
    outline_status: str
    final_review_notes_status: str
    book_output_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OutlineBase(BaseModel):
    content: str
    notes_on_outline_after: Optional[str] = None
    status: str

class OutlineCreate(BaseModel):
    book_id: UUID
    content: str

class Outline(OutlineBase):
    id: UUID
    book_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class ChapterBase(BaseModel):
    chapter_number: int
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    chapter_notes_status: str = "no"
    chapter_notes: Optional[str] = None
    status: str = "pending"

class ChapterCreate(BaseModel):
    book_id: UUID
    chapter_number: int
    title: str

class Chapter(ChapterBase):
    id: UUID
    book_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class FeedbackRequest(BaseModel):
    notes: str
    status: str # yes, no, no_notes_needed
