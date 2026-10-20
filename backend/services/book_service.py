"""Book workflow: outline -> chapters (with human-in-the-loop gates) -> final review -> compile.

Chapters are long (20 pages by default) and take several LLM calls, so they are written by a
background job. The API returns immediately with the chapter in ``generating`` state; clients
poll the chapter (or book) to follow ``progress`` until it reaches ``review_needed``.
"""
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.constants import BookOutputStatus, ChapterStatus, LogLevel, NotesStatus, OutlineStatus
from backend.database import Book, Chapter, Log, Outline, SessionLocal
from backend.services.llm_service import count_words, llm_service, parse_outline_chapters
from backend.services.notification_service import notification_service
from backend.utils.compiler import compiler, safe_filename

logger = logging.getLogger(__name__)

# Notifications hit SMTP / webhooks; never let them slow down or fail a request.
_notify_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notify")
_job_pool = ThreadPoolExecutor(max_workers=settings.MAX_CONCURRENT_JOBS, thread_name_prefix="chapter-job")


class NotFoundError(Exception):
    """Requested resource does not exist (HTTP 404)."""


class WorkflowError(Exception):
    """Action is not allowed in the book's current state (HTTP 409)."""


class BookService:
    def __init__(self) -> None:
        # chapter_id -> {"stage": str, "done": int, "total": int}; in-memory, per process.
        self._progress: dict[str, dict[str, Any]] = {}
        self._progress_lock = threading.Lock()

    # ------------------------------------------------------------- queries
    def get_book(self, db: Session, book_id: str) -> Book:
        book = db.get(Book, book_id)
        if not book:
            raise NotFoundError(f"Book '{book_id}' not found")
        return book

    def get_chapter(self, db: Session, book_id: str, chapter_number: int) -> Chapter:
        self.get_book(db, book_id)
        chapter = (
            db.query(Chapter)
            .filter(Chapter.book_id == book_id, Chapter.chapter_number == chapter_number)
            .first()
        )
        if not chapter:
            raise NotFoundError(f"Chapter {chapter_number} not found")
        return chapter

    def list_books(self, db: Session) -> list[Book]:
        return db.query(Book).order_by(Book.created_at.desc()).all()

    @staticmethod
    def latest_outline(book: Book) -> Optional[Outline]:
        return book.outlines[-1] if book.outlines else None

    def planned_chapters(self, book: Book) -> Optional[int]:
        outline = self.latest_outline(book)
        chapters = parse_outline_chapters(outline.content) if outline else []
        return len(chapters) or book.target_chapters or None

    @staticmethod
    def pages_per_chapter(book: Book) -> int:
        return book.pages_per_chapter or settings.DEFAULT_PAGES_PER_CHAPTER

    def progress(self, chapter: Chapter) -> Optional[dict[str, Any]]:
        if chapter.status != ChapterStatus.GENERATING:
            return None
        with self._progress_lock:
            return dict(self._progress.get(chapter.id) or {"stage": "Queued", "done": 0, "total": 0})

    def next_action(self, book: Book) -> str:
        if book.book_output_status == BookOutputStatus.COMPILED:
            return "Book compiled. Download the final document."
        if book.outline_status in (OutlineStatus.PENDING, OutlineStatus.GENERATING) or not book.outlines:
            return "Generate the outline."
        if book.outline_status != OutlineStatus.APPROVED:
            return "Review the outline: approve it or request changes."

        chapters = book.chapters
        last = chapters[-1] if chapters else None
        if last and last.status == ChapterStatus.GENERATING:
            return f"Chapter {last.chapter_number} is being written. This takes a few minutes."
        if last and last.status == ChapterStatus.FAILED:
            return f"Chapter {last.chapter_number} failed to generate. Retry it."
        if last and last.status != ChapterStatus.APPROVED:
            return f"Review Chapter {last.chapter_number}: approve it or request changes."

        planned = self.planned_chapters(book)
        if not chapters or (planned and len(chapters) < planned):
            return f"Generate Chapter {len(chapters) + 1}."
        if book.final_review_notes_status != NotesStatus.NO_NOTES_NEEDED:
            return "Complete the final review."
        return "Compile the book."

    # ------------------------------------------------------------- outline
    def create_book(
        self,
        db: Session,
        title: str,
        notes_before: str,
        target_chapters: Optional[int] = None,
        pages_per_chapter: Optional[int] = None,
    ) -> Book:
        if not notes_before or not notes_before.strip():
            raise WorkflowError("notes_on_outline_before is required before generating an outline")

        book = Book(
            title=title,
            notes_on_outline_before=notes_before,
            outline_status=OutlineStatus.PENDING,
            target_chapters=target_chapters or settings.DEFAULT_CHAPTERS,
            pages_per_chapter=pages_per_chapter or settings.DEFAULT_PAGES_PER_CHAPTER,
        )
        db.add(book)
        db.commit()
        db.refresh(book)
        self._log(
            db, book,
            f"Book created: '{title}' ({book.target_chapters} chapters × ~{book.pages_per_chapter} pages)",
        )
        return self.generate_outline(db, book.id)

    def generate_outline(self, db: Session, book_id: str) -> Book:
        """Generate the first outline. Safe to retry if a previous attempt failed."""
        book = self.get_book(db, book_id)
        if book.outlines:
            raise WorkflowError("An outline already exists. Use outline feedback to revise it.")
        if not (book.notes_on_outline_before or "").strip():
            raise WorkflowError("notes_on_outline_before is required before generating an outline")

        book.outline_status = OutlineStatus.GENERATING
        db.commit()
        try:
            content = llm_service.generate_outline(
                book.title, book.notes_on_outline_before, book.target_chapters or settings.DEFAULT_CHAPTERS
            )
        except Exception:
            book.outline_status = OutlineStatus.PENDING
            db.commit()
            self._log(db, book, "Outline generation failed", LogLevel.ERROR)
            raise

        db.add(Outline(book_id=book.id, content=content, status=OutlineStatus.REVIEW_NEEDED))
        book.outline_status = OutlineStatus.REVIEW_NEEDED
        db.commit()
        db.refresh(book)
        self._log(db, book, "Outline generated and awaiting review")
        self._notify("Outline Ready", book.title, "The outline has been generated and needs your review.")
        return book

    def provide_outline_feedback(self, db: Session, book_id: str, notes: str, status: str) -> str:
        book = self.get_book(db, book_id)
        outline = self.latest_outline(book)
        if not outline:
            raise WorkflowError("No outline exists yet. Generate the outline first.")

        if status == NotesStatus.YES:
            if book.chapters:
                raise WorkflowError("The outline cannot be revised after chapters have been generated.")
            new_content = llm_service.regenerate_outline(
                book.title, outline.content, notes, book.target_chapters or settings.DEFAULT_CHAPTERS
            )
            db.add(
                Outline(
                    book_id=book.id,
                    content=new_content,
                    notes_on_outline_after=notes,
                    status=OutlineStatus.REVIEW_NEEDED,
                )
            )
            book.outline_status = OutlineStatus.REVIEW_NEEDED
            db.commit()
            self._log(db, book, f"Outline revised with editor notes: {notes}")
            self._notify("Outline Regenerated", book.title, "A revised outline is ready for review.")
            return "Outline regenerated with your notes. Please review the new version."

        if status == NotesStatus.NO_NOTES_NEEDED:
            outline.status = OutlineStatus.APPROVED
            book.outline_status = OutlineStatus.APPROVED
            db.commit()
            self._log(db, book, "Outline approved")
            return "Outline approved. You can now generate chapters."

        # status == no: keep waiting for the editor
        book.outline_status = OutlineStatus.REVIEW_NEEDED
        db.commit()
        self._log(db, book, "Outline review paused, waiting for editor notes", LogLevel.WARNING)
        return "Outline is on hold until notes are provided or it is approved."

    # ------------------------------------------------------------ chapters
    def generate_next_chapter(self, db: Session, book_id: str) -> Chapter:
        """Start writing the next chapter (or retry a failed one) in the background."""
        book = self.get_book(db, book_id)
        if book.outline_status != OutlineStatus.APPROVED:
            raise WorkflowError("The outline must be approved before generating chapters.")

        chapters = book.chapters
        last = chapters[-1] if chapters else None
        if last and last.status == ChapterStatus.GENERATING:
            raise WorkflowError(f"Chapter {last.chapter_number} is still being written.")

        if last and last.status == ChapterStatus.FAILED:
            chapter = last  # retry in place; re-apply notes if the failed job was a rewrite
            notes = last.chapter_notes if last.chapter_notes_status == NotesStatus.YES else None
        else:
            if last and last.status != ChapterStatus.APPROVED:
                raise WorkflowError(
                    f"Chapter {last.chapter_number} must be approved before generating the next chapter."
                )
            planned = self.planned_chapters(book)
            next_num = len(chapters) + 1
            if planned and next_num > planned:
                raise WorkflowError(f"All {planned} chapters in the outline have been written.")
            title = dict(parse_outline_chapters(self._approved_outline(book).content)).get(next_num)
            chapter = Chapter(book_id=book.id, chapter_number=next_num, title=title or f"Chapter {next_num}")
            db.add(chapter)
            notes = None

        chapter.status = ChapterStatus.GENERATING
        chapter.chapter_notes_status = NotesStatus.YES if notes else NotesStatus.NO
        self._reset_final_review(book)
        db.commit()
        db.refresh(chapter)
        self._log(db, book, f"Started writing Chapter {chapter.chapter_number} (~{self.pages_per_chapter(book)} pages)")
        self._start_job(chapter.id, notes)
        return chapter

    def provide_chapter_feedback(
        self, db: Session, book_id: str, chapter_number: int, notes: str, status: str
    ) -> str:
        book = self.get_book(db, book_id)
        chapter = self.get_chapter(db, book_id, chapter_number)
        if chapter.status == ChapterStatus.GENERATING:
            raise WorkflowError(f"Chapter {chapter_number} is still being written. Wait until it is finished.")
        if chapter.status == ChapterStatus.FAILED:
            raise WorkflowError(f"Chapter {chapter_number} failed to generate. Retry generation first.")

        if status == NotesStatus.YES:
            later = [c for c in book.chapters if c.chapter_number > chapter_number]
            if later:
                raise WorkflowError(
                    f"Chapter {chapter_number} cannot be revised because later chapters build on it."
                )
            chapter.chapter_notes = notes
            chapter.chapter_notes_status = NotesStatus.YES
            chapter.status = ChapterStatus.GENERATING
            self._reset_final_review(book)
            db.commit()
            self._log(db, book, f"Rewriting Chapter {chapter_number} with editor notes: {notes}")
            self._start_job(chapter.id, notes)
            return f"Chapter {chapter_number} is being rewritten with your notes. This takes a few minutes."

        if status == NotesStatus.NO_NOTES_NEEDED:
            chapter.chapter_notes_status = NotesStatus.NO_NOTES_NEEDED
            chapter.status = ChapterStatus.APPROVED
            db.commit()
            self._log(db, book, f"Chapter {chapter_number} approved")
            return f"Chapter {chapter_number} approved."

        chapter.chapter_notes_status = NotesStatus.NO
        chapter.status = ChapterStatus.REVIEW_NEEDED
        db.commit()
        self._log(db, book, f"Chapter {chapter_number} paused, waiting for editor notes", LogLevel.WARNING)
        return f"Chapter {chapter_number} is on hold until notes are provided or it is approved."

    def recover_interrupted_jobs(self) -> int:
        """Mark chapters left in `generating` by a previous process (e.g. a restart) as failed."""
        with SessionLocal() as db:
            stuck = db.query(Chapter).filter(Chapter.status == ChapterStatus.GENERATING).all()
            for chapter in stuck:
                chapter.status = ChapterStatus.FAILED
                db.add(Log(book_id=chapter.book_id, level=LogLevel.ERROR,
                           message=f"Chapter {chapter.chapter_number} was interrupted by a server restart"))
            db.commit()
            return len(stuck)

    # --------------------------------------------------- background writer
    def _start_job(self, chapter_id: str, notes: Optional[str]) -> None:
        self._set_progress(chapter_id, "Queued", 0, 0)
        _job_pool.submit(self._write_chapter, chapter_id, notes)

    def _set_progress(self, chapter_id: str, stage: str, done: int, total: int) -> None:
        with self._progress_lock:
            self._progress[chapter_id] = {"stage": stage, "done": done, "total": total}

    def _write_chapter(self, chapter_id: str, notes: Optional[str]) -> None:
        db = SessionLocal()
        try:
            chapter = db.get(Chapter, chapter_id)
            book = chapter.book
            num = chapter.chapter_number
            outline = self._approved_outline(book).content
            previous = [c for c in book.chapters if c.chapter_number < num]
            summaries = self._summaries(previous)

            target_words = self.pages_per_chapter(book) * settings.WORDS_PER_PAGE
            n_sections = max(1, math.ceil(target_words / settings.SECTION_WORDS))
            section_words = round(target_words / n_sections)
            total_steps = n_sections + 2  # plan + sections + summary

            self._set_progress(chapter_id, "Planning the chapter", 0, total_steps)
            previous_plan = [ln[3:] for ln in (chapter.content or "").splitlines() if ln.startswith("## ")]
            title, plan = llm_service.plan_chapter(
                book.title, outline, num, summaries, n_sections, notes=notes, previous_plan=previous_plan
            )

            parts: list[str] = []
            for i, (heading, _brief) in enumerate(plan):
                self._set_progress(chapter_id, f"Writing section {i + 1} of {n_sections}: {heading}", i + 1, total_steps)
                text = llm_service.write_section(
                    book.title, outline, num, title, plan, i, summaries,
                    recent_text=parts[-1] if parts else "", words=section_words, notes=notes,
                )
                parts.append(f"## {heading}\n\n{text.strip()}")

            content = "\n\n".join(parts)
            self._set_progress(chapter_id, "Summarising for continuity", total_steps - 1, total_steps)
            summary = llm_service.summarize_chapter(f"# Chapter {num}: {title}\n\n{content}")

            chapter.title, chapter.content, chapter.summary = title, content, summary
            chapter.status = ChapterStatus.REVIEW_NEEDED
            chapter.chapter_notes_status = NotesStatus.NO
            db.commit()
            words = count_words(content)
            verb = "rewritten" if notes else "written"
            self._log(db, book, f"Chapter {num} {verb}: '{title}' ({words:,} words, ~{words / settings.WORDS_PER_PAGE:.0f} pages)")
            self._notify("Chapter Ready", book.title, f"Chapter {num} ('{title}') is ready for review.")
        except Exception as exc:  # noqa: BLE001 - background job must record any failure
            logger.exception("Chapter job %s failed", chapter_id)
            db.rollback()
            chapter = db.get(Chapter, chapter_id)
            if chapter:
                chapter.status = ChapterStatus.FAILED
                db.commit()
                self._log(db, chapter.book, f"Chapter {chapter.chapter_number} failed: {exc}", LogLevel.ERROR)
        finally:
            with self._progress_lock:
                self._progress.pop(chapter_id, None)
            db.close()

    # ------------------------------------------------- final review/compile
    def provide_final_review_feedback(self, db: Session, book_id: str, notes: str, status: str) -> str:
        book = self.get_book(db, book_id)
        if not book.chapters:
            raise WorkflowError("Generate at least one chapter before the final review.")
        pending = [c.chapter_number for c in book.chapters if c.status != ChapterStatus.APPROVED]
        if pending:
            raise WorkflowError(f"Approve all chapters before the final review (pending: {pending}).")

        book.final_review_notes_status = status
        if status == NotesStatus.NO_NOTES_NEEDED:
            book.book_output_status = BookOutputStatus.READY
            db.commit()
            self._log(db, book, "Final review approved; book is ready to compile")
            self._notify("Final Review Approved", book.title, "The book is ready to be compiled.")
            return "Final review approved. You can now compile the book."

        book.book_output_status = BookOutputStatus.IN_PROGRESS
        db.commit()
        detail = f": {notes}" if notes else ""
        self._log(db, book, f"Final review on hold{detail}", LogLevel.WARNING)
        self._notify("Final Review Paused", book.title, notes or "Waiting for final review notes.")
        return "Final review is on hold. Address the notes, then approve the final review."

    def compile_book(self, db: Session, book_id: str) -> Path:
        book = self.get_book(db, book_id)
        if book.final_review_notes_status != NotesStatus.NO_NOTES_NEEDED:
            raise WorkflowError("The final review must be approved (no_notes_needed) before compiling.")
        if not book.chapters:
            raise WorkflowError("No chapters found to compile.")

        path = self.export_path(book)
        compiler.compile_to_docx(
            book.title,
            [{"chapter_number": c.chapter_number, "title": c.title, "content": c.content} for c in book.chapters],
            path,
        )
        book.book_output_status = BookOutputStatus.COMPILED
        db.commit()
        self._log(db, book, f"Book compiled to {path.name}")
        self._notify("Book Compiled", book.title, f"Final draft saved as {path.name}")
        return path

    @staticmethod
    def export_path(book: Book) -> Path:
        # Include a short id so two books with the same title never overwrite each other.
        name = safe_filename(f"{book.title} {book.id[:8]}", "docx")
        return Path(settings.EXPORT_DIR) / name

    def delete_book(self, db: Session, book_id: str) -> None:
        book = self.get_book(db, book_id)
        if any(c.status == ChapterStatus.GENERATING for c in book.chapters):
            raise WorkflowError("A chapter is still being written. Wait for it to finish before deleting.")
        db.delete(book)
        db.commit()

    # ------------------------------------------------------------- helpers
    def _approved_outline(self, book: Book) -> Outline:
        approved = [o for o in book.outlines if o.status == OutlineStatus.APPROVED]
        outline = approved[-1] if approved else self.latest_outline(book)
        if not outline:
            raise WorkflowError("Outline not found.")
        return outline

    @staticmethod
    def _summaries(chapters: list[Chapter]) -> str:
        return "\n".join(
            f"Chapter {c.chapter_number} ({c.title}): {c.summary}" for c in chapters if c.summary
        )

    @staticmethod
    def _reset_final_review(book: Book) -> None:
        book.final_review_notes_status = NotesStatus.NO
        book.book_output_status = BookOutputStatus.IN_PROGRESS

    @staticmethod
    def _log(db: Session, book: Book, message: str, level: str = LogLevel.INFO) -> None:
        db.add(Log(book_id=book.id, message=message, level=level))
        db.commit()
        logger.log(logging.WARNING if level != LogLevel.INFO else logging.INFO, "[%s] %s", book.id[:8], message)

    @staticmethod
    def _notify(event: str, title: str, details: str) -> None:
        _notify_pool.submit(notification_service.notify_event, event, title, details)


book_service = BookService()
