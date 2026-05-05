from uuid import UUID
from backend.database import SessionLocal, Book, Outline, Chapter
from backend.services.llm_service import llm_service
from backend.services.notification_service import notification_service
from backend.utils.compiler import compiler
import os

class BookService:
    async def create_book(self, title: str, notes_before: str):
        db = SessionLocal()
        try:
            # Validation: Only generate outline if notes_on_outline_before exists
            if not notes_before or notes_before.strip() == "":
                raise ValueError("notes_on_outline_before is required before generating outline")
            
            # 1. Create book record
            book = Book(
                title=title,
                notes_on_outline_before=notes_before,
                outline_status="generating"
            )
            db.add(book)
            db.commit()
            db.refresh(book)
            
            # 2. Trigger initial outline generation
            outline_content = await llm_service.generate_outline(title, notes_before)
            
            # 3. Store outline
            outline = Outline(
                book_id=book.id,
                content=outline_content,
                status="review_needed"
            )
            db.add(outline)
            db.commit()
            
            # 4. Update book status
            book.outline_status = "review_needed"
            db.commit()
            
            # 5. Notify
            notification_service.notify_event("Outline Ready", title, "The outline has been generated and needs your review.")
            
            return {"id": book.id, "title": book.title, "outline_status": book.outline_status}
            
        finally:
            db.close()

    async def provide_outline_feedback(self, book_id: str, notes: str, status: str):
        db = SessionLocal()
        try:
            # status: yes (regenerate), no_notes_needed (proceed)
            book = db.query(Book).filter(Book.id == book_id).first()
            if not book:
                raise ValueError("Book not found")
            
            if status == "yes":
                # Regenerate
                outline = db.query(Outline).filter(Outline.book_id == book_id).order_by(Outline.created_at.desc()).first()
                if not outline:
                    raise ValueError("Outline not found")
                
                current_outline = outline.content
                
                new_outline = await llm_service.regenerate_outline(book.title, current_outline, notes)
                
                # Create new outline version
                new_outline_record = Outline(
                    book_id=book_id,
                    content=new_outline,
                    notes_on_outline_after=notes,
                    status="review_needed"
                )
                db.add(new_outline_record)
                db.commit()
                
                notification_service.notify_event("Outline Regenerated", book.title, "Revised outline is ready.")
                return {"message": "Outline regenerated"}
                
            elif status == "no_notes_needed":
                # Approve and move to chapters
                book.outline_status = "approved"
                db.commit()
                return {"message": "Outline approved. You can now start chapter generation."}
            
            return {"message": "Status updated"}
        finally:
            db.close()

    async def generate_next_chapter(self, book_id: str):
        db = SessionLocal()
        try:
            book = db.query(Book).filter(Book.id == book_id).first()
            if not book:
                raise ValueError("Book not found")
            
            # Check last chapter status
            last_chapter = db.query(Chapter).filter(Chapter.book_id == book_id).order_by(Chapter.chapter_number.desc()).first()
            
            if last_chapter:
                if last_chapter.chapter_notes_status == 'yes':
                    raise ValueError(f"Chapter {last_chapter.chapter_number} is waiting for notes.")
                if last_chapter.chapter_notes_status == 'no':
                    raise ValueError(f"Chapter {last_chapter.chapter_number} needs approval.")
            
            # Get outline
            outline = db.query(Outline).filter(Outline.book_id == book_id, Outline.status == "approved").order_by(Outline.created_at.desc()).first()
            if not outline:
                outline = db.query(Outline).filter(Outline.book_id == book_id).order_by(Outline.created_at.desc()).first()
            
            if not outline:
                raise ValueError("Outline not found")
            
            # Get existing chapters for context
            existing_chapters = db.query(Chapter).filter(Chapter.book_id == book_id).order_by(Chapter.chapter_number).all()
            next_num = len(existing_chapters) + 1
            
            # Build context
            summaries = "\n".join([f"Ch {c.chapter_number}: {c.summary}" for c in existing_chapters if c.summary])
            
            # Generate
            content = await llm_service.generate_chapter(book.title, outline.content, next_num, summaries)
            summary = await llm_service.summarize_chapter(content)
            
            # Store
            chapter = Chapter(
                book_id=book_id,
                chapter_number=next_num,
                title=f"Chapter {next_num}",
                content=content,
                summary=summary,
                status="review_needed",
                chapter_notes_status="no"
            )
            db.add(chapter)
            db.commit()
            db.refresh(chapter)
            
            notification_service.notify_event("Chapter Ready", book.title, f"Chapter {next_num} is ready for review.")
            return {"id": chapter.id, "chapter_number": chapter.chapter_number, "title": chapter.title}
        finally:
            db.close()

    async def provide_chapter_feedback(self, book_id: str, chapter_number: int, notes: str, status: str):
        db = SessionLocal()
        try:
            # status: yes (regenerate), no_notes_needed (proceed)
            chapter = db.query(Chapter).filter(Chapter.book_id == book_id, Chapter.chapter_number == chapter_number).first()
            if not chapter:
                raise ValueError(f"Chapter {chapter_number} not found")
            
            if status == "yes":
                # Regenerate chapter
                book = db.query(Book).filter(Book.id == book_id).first()
                
                # Get outline
                outline = db.query(Outline).filter(Outline.book_id == book_id).order_by(Outline.created_at.desc()).first()
                
                # Get previous chapters for context
                existing_chapters = db.query(Chapter).filter(Chapter.book_id == book_id, Chapter.chapter_number < chapter_number).order_by(Chapter.chapter_number).all()
                summaries = "\n".join([f"Ch {c.chapter_number}: {c.summary}" for c in existing_chapters if c.summary])
                
                # Regenerate
                new_content = await llm_service.regenerate_chapter(book.title, outline.content, chapter_number, chapter.content, summaries, notes)
                new_summary = await llm_service.summarize_chapter(new_content)
                
                # Update chapter
                chapter.content = new_content
                chapter.summary = new_summary
                chapter.chapter_notes = notes
                chapter.chapter_notes_status = "no"
                chapter.status = "review_needed"
                db.commit()
                
                notification_service.notify_event("Chapter Regenerated", book.title, f"Chapter {chapter_number} has been revised.")
                return {"message": f"Chapter {chapter_number} regenerated"}
                
            elif status == "no_notes_needed":
                # Approve chapter
                chapter.chapter_notes_status = "no_notes_needed"
                chapter.status = "approved"
                db.commit()
                return {"message": f"Chapter {chapter_number} approved. You can generate the next chapter."}
            
            return {"message": "Status updated"}
        finally:
            db.close()

    async def provide_final_review_feedback(self, book_id: str, notes: str, status: str):
        db = SessionLocal()
        try:
            # status: no_notes_needed (proceed to compile), yes (wait for notes)
            book = db.query(Book).filter(Book.id == book_id).first()
            if not book:
                raise ValueError("Book not found")
            
            if status == "yes":
                book.final_review_notes_status = "yes"
                db.commit()
                return {"message": "Waiting for final review notes."}
            elif status == "no_notes_needed":
                book.final_review_notes_status = "no_notes_needed"
                db.commit()
                return {"message": "Final review approved. You can now compile the book."}
            
            return {"message": "Status updated"}
        finally:
            db.close()

    async def compile_book(self, book_id: str):
        db = SessionLocal()
        try:
            book = db.query(Book).filter(Book.id == book_id).first()
            if not book:
                raise ValueError("Book not found")
            
            # Check final review status
            if book.final_review_notes_status != "no_notes_needed":
                raise ValueError("Final review must be approved (no_notes_needed) before compiling.")
            
            chapters = db.query(Chapter).filter(Chapter.book_id == book_id).order_by(Chapter.chapter_number).all()
            
            if not chapters:
                raise ValueError("No chapters found to compile.")
            
            filename = f"{book.title.replace(' ', '_')}.docx"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            # Convert chapters to dict format for compiler
            chapters_dict = [
                {
                    "chapter_number": c.chapter_number,
                    "title": c.title,
                    "content": c.content
                }
                for c in chapters
            ]
            
            compiler.compile_to_docx(book.title, chapters_dict, filepath)
            
            book.book_output_status = "compiled"
            db.commit()
            
            notification_service.notify_event("Book Compiled", book.title, f"Final draft saved as {filename}")
            return {"file_path": filepath}
        finally:
            db.close()

book_service = BookService()
