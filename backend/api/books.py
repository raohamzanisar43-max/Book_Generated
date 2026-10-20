"""Book workflow REST endpoints.

Handlers are synchronous on purpose: FastAPI runs them in a worker thread pool, so
long-running LLM calls and database I/O never block the event loop.
"""
from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Book, Chapter, get_db
from backend.models import (
    BookCreate,
    BookOut,
    BookSummaryOut,
    ChapterOut,
    CompileResponse,
    FeedbackRequest,
    LogOut,
    MessageResponse,
)
from backend.services.book_service import NotFoundError, book_service
from backend.services.llm_service import count_words

router = APIRouter(prefix="/books", tags=["Books"])


def _chapter(chapter: Chapter, with_content: bool = False) -> dict:
    words = count_words(chapter.content)
    data = {
        "id": chapter.id,
        "chapter_number": chapter.chapter_number,
        "title": chapter.title,
        "status": chapter.status,
        "chapter_notes_status": chapter.chapter_notes_status,
        "created_at": chapter.created_at,
        "word_count": words,
        "estimated_pages": round(words / settings.WORDS_PER_PAGE, 1),
        "progress": book_service.progress(chapter),
    }
    if with_content:
        data.update(content=chapter.content, summary=chapter.summary, chapter_notes=chapter.chapter_notes)
    return data


def _summary(book: Book) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "outline_status": book.outline_status,
        "final_review_notes_status": book.final_review_notes_status,
        "book_output_status": book.book_output_status,
        "chapters_written": len(book.chapters),
        "chapters_planned": book_service.planned_chapters(book),
        "target_chapters": book.target_chapters,
        "pages_per_chapter": book_service.pages_per_chapter(book),
        "total_words": sum(count_words(c.content) for c in book.chapters),
        "created_at": book.created_at,
        "updated_at": book.updated_at,
    }


def _detail(book: Book) -> dict:
    return {
        **_summary(book),
        "notes_on_outline_before": book.notes_on_outline_before,
        "outlines": book.outlines,
        "chapters": [_chapter(c) for c in book.chapters],
        "next_action": book_service.next_action(book),
    }


# ------------------------------------------------------------------ books
@router.post("/", response_model=BookOut, status_code=status.HTTP_201_CREATED, summary="Create a book")
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    """Create a book and generate its first outline from `notes_on_outline_before`."""
    book = book_service.create_book(
        db, payload.title, payload.notes_on_outline_before, payload.target_chapters, payload.pages_per_chapter
    )
    return _detail(book)


@router.get("/", response_model=list[BookSummaryOut], summary="List books")
def list_books(db: Session = Depends(get_db)):
    return [_summary(b) for b in book_service.list_books(db)]


@router.get("/{book_id}", response_model=BookOut, summary="Get a book")
def get_book(book_id: str, db: Session = Depends(get_db)):
    return _detail(book_service.get_book(db, book_id))


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a book")
def delete_book(book_id: str, db: Session = Depends(get_db)):
    book_service.delete_book(db, book_id)


@router.get("/{book_id}/logs", response_model=list[LogOut], summary="Activity log")
def get_logs(book_id: str, db: Session = Depends(get_db)):
    return book_service.get_book(db, book_id).logs


# ---------------------------------------------------------------- outline
@router.post("/{book_id}/outline/generate", response_model=BookOut, summary="(Re)try outline generation")
def generate_outline(book_id: str, db: Session = Depends(get_db)):
    """Generate the initial outline if a previous attempt failed (e.g. LLM outage)."""
    return _detail(book_service.generate_outline(db, book_id))


@router.post("/{book_id}/outline-feedback", response_model=MessageResponse, summary="Review the outline")
def outline_feedback(book_id: str, feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """`yes` + notes regenerates the outline, `no_notes_needed` approves it, `no` pauses."""
    return {"message": book_service.provide_outline_feedback(db, book_id, feedback.notes, feedback.status)}


# --------------------------------------------------------------- chapters
@router.post(
    "/{book_id}/chapters/generate",
    response_model=ChapterOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate the next chapter",
)
def generate_chapter(book_id: str, db: Session = Depends(get_db)):
    """Start writing the next chapter (or retry a failed one) in the background.

    Returns immediately with `status: generating`. Poll `GET /books/{id}/chapters/{n}` and watch
    `progress` until the status becomes `review_needed` (or `failed`).
    """
    return _chapter(book_service.generate_next_chapter(db, book_id), with_content=True)


@router.get("/{book_id}/chapters/{chapter_number}", response_model=ChapterOut, summary="Get a chapter")
def get_chapter(book_id: str, chapter_number: int, db: Session = Depends(get_db)):
    return _chapter(book_service.get_chapter(db, book_id, chapter_number), with_content=True)


@router.post(
    "/{book_id}/chapters/{chapter_number}/feedback",
    response_model=MessageResponse,
    summary="Review a chapter",
)
def chapter_feedback(book_id: str, chapter_number: int, feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """`yes` + notes regenerates the chapter, `no_notes_needed` approves it, `no` pauses."""
    message = book_service.provide_chapter_feedback(db, book_id, chapter_number, feedback.notes, feedback.status)
    return {"message": message}


# ---------------------------------------------------------- final output
@router.post("/{book_id}/final-review", response_model=MessageResponse, summary="Final review")
def final_review(book_id: str, feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """`no_notes_needed` approves the book for compilation; `yes`/`no` keeps it on hold."""
    return {"message": book_service.provide_final_review_feedback(db, book_id, feedback.notes, feedback.status)}


@router.post("/{book_id}/compile", response_model=CompileResponse, summary="Compile to .docx")
def compile_book(book_id: str, db: Session = Depends(get_db)):
    path = book_service.compile_book(db, book_id)
    return {
        "message": "Book compiled successfully.",
        "file_name": path.name,
        "file_path": str(path),
        "download_url": f"/books/{book_id}/download",
    }


@router.get("/{book_id}/download", summary="Download the compiled .docx", response_class=FileResponse)
def download_book(book_id: str, db: Session = Depends(get_db)):
    book = book_service.get_book(db, book_id)
    path = book_service.export_path(book)
    if not path.exists():
        raise NotFoundError("The book has not been compiled yet.")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

