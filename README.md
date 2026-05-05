# Automated Book Generation System

A modular and scalable book-generation system built with FastAPI, PostgreSQL, and LLM automation.

## Features
- **Stage 1: Outline Generation**: Generate and refine book outlines with human-in-the-loop feedback.
- **Stage 2: Chapter Generation**: Context-aware chapter writing using previous chapter summaries.
- **Stage 3: Final Compilation**: Compile all chapters into a professional `.docx` document.
- **Notification System**: Integrated Email and MS Teams notifications for workflow events.

## Tech Stack
- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL (local or cloud)
- **ORM**: SQLAlchemy
- **AI Models**: OpenAI (GPT-4o) / Google Gemini
- **Output**: python-docx
- **Notifications**: SMTP & MS Teams Webhooks

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Rename `.env.example` to `.env` and fill in your credentials:
   - `DATABASE_URL` - PostgreSQL connection string
   - `OPENAI_API_KEY` or `GEMINI_API_KEY`
   - `SMTP_*` for email notifications (optional)
   - `TEAMS_WEBHOOK_URL` for Teams notifications (optional)

3. **Database Setup**:
   ```bash
   python init_db.py
   ```
   This will create all required tables in your PostgreSQL database.

4. **Run the Application**:
   ```bash
   uvicorn backend.main:app --reload
   ```

## API Endpoints

### Book Management
- `POST /books/` - Create book with title and notes_on_outline_before
- `GET /books/` - List all books
- `GET /books/{book_id}` - Get book details with outline and chapters

### Outline Workflow
- `POST /books/{book_id}/outline-feedback` - Provide outline feedback (status: yes/no_notes_needed)

### Chapter Workflow
- `POST /books/{book_id}/chapters/generate` - Generate next chapter
- `GET /books/{book_id}/chapters/{chapter_number}` - Get chapter details
- `POST /books/{book_id}/chapters/{chapter_number}/feedback` - Provide chapter feedback (status: yes/no_notes_needed)

### Final Compilation
- `POST /books/{book_id}/final-review` - Final review approval (status: no_notes_needed)
- `POST /books/{book_id}/compile` - Compile final .docx file

## Workflow Guide

1. Create book with title + notes_on_outline_before (required)
2. Review outline → approve with status "no_notes_needed"
3. Generate chapters one by one
4. For each chapter: review → approve with status "no_notes_needed"
5. Final review → approve with status "no_notes_needed"
6. Compile book to .docx

## Testing
- `python test_db.py` - Test database connection
- `python test_llm.py` - Test LLM configuration
- `python test_workflow.py` - Test complete workflow (requires server running)
