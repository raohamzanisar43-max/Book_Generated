# Project Summary: Automated Book Generation System

## What it does
A FastAPI service and web dashboard that writes a book with an LLM while a human editor approves
every stage: **outline → chapters (one at a time, context-chained) → final review → .docx**.

## Architecture

| Layer | Module | Responsibility |
|-------|--------|----------------|
| HTTP | `backend/api/books.py`, `backend/main.py` | REST endpoints, error mapping (404/409/422/503), health, dashboard |
| Workflow | `backend/services/book_service.py` | State machine and approval gates, activity logging |
| LLM | `backend/services/llm_service.py` | Prompts; OpenAI → Gemini fallback; offline `mock` provider |
| Output | `backend/utils/compiler.py` | Markdown → formatted .docx (title page, contents, chapters) |
| Notifications | `backend/services/notification_service.py` | SMTP email + MS Teams webhook (background, non-blocking) |
| Persistence | `backend/database.py`, `database/schema.sql` | PostgreSQL via SQLAlchemy: `books`, `outlines`, `chapters`, `logs` |
| UI | `backend/static/` | Dependency-free dashboard served at `/` |

## Key design decisions
- **Human-in-the-loop gates** are enforced server-side, not only in the UI. Breaking a rule returns `409 Conflict`
  with a readable message.
- **Context chaining**: every chapter stores a short summary. The summaries of earlier chapters are passed
  to the prompt for later ones, so the book stays consistent without sending the full manuscript each time.
- **Versioned outlines**: each revision is a new row, so the editing history is kept.
- **Failures are explicit**: if no LLM provider succeeds, the API returns 503 and nothing is saved.
  Placeholder text is never stored as content.
- **Sync handlers in a thread pool**: long LLM calls never block the event loop.

## Quality
- `pytest` suite (23 tests) that covers the full workflow, every gate, validation and .docx output.
  It runs offline on SQLite with the mock LLM.
- Docker image and `docker compose` stack (API + PostgreSQL).

## Deliverables checklist
1. Source code (this repository)
2. Database structure: `database/schema.sql`
3. Example output: compile a book, then look in `exports/`
4. API documentation: Swagger UI at http://localhost:8010/docs
5. Demo: dashboard at http://localhost:8010, or `python -m scripts.demo_workflow`
