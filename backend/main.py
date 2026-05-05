from fastapi import FastAPI, HTTPException, Depends
from typing import List
from uuid import UUID
from backend.models import Book, BookCreate, FeedbackRequest, Chapter
from backend.services.book_service import book_service
from backend.database import SessionLocal, Book as DBBook, Outline, Chapter as DBChapter

app = FastAPI(title="Automated Book Generation System")

@app.get("/")
async def root():
    return {"message": "Welcome to the Automated Book Generation System"}

@app.post("/books/", response_model=dict)
async def create_book(book: BookCreate):
    return await book_service.create_book(book.title, book.notes_on_outline_before)

@app.get("/books/", response_model=List[dict])
async def list_books():
    db = SessionLocal()
    try:
        books = db.query(DBBook).all()
        return [{"id": b.id, "title": b.title, "outline_status": b.outline_status, "book_output_status": b.book_output_status} for b in books]
    finally:
        db.close()

@app.get("/books/{book_id}", response_model=dict)
async def get_book(book_id: str):
    db = SessionLocal()
    try:
        book = db.query(DBBook).filter(DBBook.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        
        outlines = db.query(Outline).filter(Outline.book_id == book_id).all()
        chapters = db.query(DBChapter).filter(DBChapter.book_id == book_id).all()
        
        return {
            "id": book.id,
            "title": book.title,
            "notes_on_outline_before": book.notes_on_outline_before,
            "outline_status": book.outline_status,
            "final_review_notes_status": book.final_review_notes_status,
            "book_output_status": book.book_output_status,
            "outlines": [{"id": o.id, "content": o.content, "status": o.status} for o in outlines],
            "chapters": [{"id": c.id, "chapter_number": c.chapter_number, "title": c.title, "status": c.status} for c in chapters]
        }
    finally:
        db.close()

@app.post("/books/{book_id}/outline-feedback")
async def outline_feedback(book_id: str, feedback: FeedbackRequest):
    return await book_service.provide_outline_feedback(book_id, feedback.notes, feedback.status)

@app.post("/books/{book_id}/chapters/generate")
async def generate_chapter(book_id: str):
    db = SessionLocal()
    try:
        # Check if outline is approved
        book = db.query(DBBook).filter(DBBook.id == book_id).first()
        if not book or book.outline_status != "approved":
            raise HTTPException(status_code=400, detail="Outline must be approved before generating chapters.")
        return await book_service.generate_next_chapter(book_id)
    finally:
        db.close()

@app.post("/books/{book_id}/compile")
async def compile_book(book_id: str):
    return await book_service.compile_book(book_id)

@app.post("/books/{book_id}/chapters/{chapter_number}/feedback")
async def chapter_feedback(book_id: str, chapter_number: int, feedback: FeedbackRequest):
    return await book_service.provide_chapter_feedback(book_id, chapter_number, feedback.notes, feedback.status)

@app.get("/books/{book_id}/chapters/{chapter_number}")
async def get_chapter(book_id: str, chapter_number: int):
    db = SessionLocal()
    try:
        chapter = db.query(DBChapter).filter(DBChapter.book_id == book_id, DBChapter.chapter_number == chapter_number).first()
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        return {
            "id": chapter.id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "content": chapter.content,
            "summary": chapter.summary,
            "chapter_notes_status": chapter.chapter_notes_status,
            "chapter_notes": chapter.chapter_notes,
            "status": chapter.status
        }
    finally:
        db.close()

@app.post("/books/{book_id}/final-review")
async def final_review(book_id: str, feedback: FeedbackRequest):
    return await book_service.provide_final_review_feedback(book_id, feedback.notes, feedback.status)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
