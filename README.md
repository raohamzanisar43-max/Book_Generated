# Automated Book Generation System

Generate complete books with an LLM through a **human-in-the-loop** workflow. An editor stays in control:
every stage waits for approval before the next one starts, and any stage can be revised with notes.

```
 Title + editor notes ──► Outline ──► Chapter 1 ──► Chapter 2 ──► … ──► Final review ──► .docx
                          ▲    │       ▲     │       ▲     │                  │
                          └────┘       └─────┘       └─────┘                  │
                       revise w/ notes   revise w/ notes            hold w/ notes / approve
```

**Stack:** FastAPI · SQLAlchemy 2 · PostgreSQL · OpenAI / Google Gemini · python-docx · SMTP + MS Teams

## Features

- **Web dashboard** at `/`: create books, review and approve outlines and chapters, follow progress, and download the result.
- **Outline stage**: an outline is generated from `notes_on_outline_before`, which is mandatory. Every revision is stored as a new version.
- **Long-form chapters**: each chapter is about **20 pages (~10,000 words)** by default. You can set the number of chapters (1–40) and pages per chapter (1–40) for each book. A model can't write that much reliably in one response, so each chapter is first **planned as sections**, then **written one section at a time**. Every section gets the plan, the summaries of earlier chapters and the end of the previous section, so the chapter reads as one continuous text.
- **Background generation**: chapter writing runs as a background job. The dashboard shows live progress, such as "Writing section 4 of 10". A failed job can be retried, and jobs interrupted by a server restart are marked as failed.
- **Chapter stage**: chapters are written one at a time. Each chapter gets summaries of the chapters before it, so the book stays consistent. Chapter *N+1* can't be generated until chapter *N* is approved.
- **Final review → compile**: the manuscript is exported as a formatted Word document, with a title page, a table of contents, headings, lists and bold/italic text converted from Markdown.
- **Multiple LLM providers**: OpenAI and Gemini, with automatic fallback between them, plus a `mock` provider that runs offline for demos and tests.
- **Notifications**: email and MS Teams messages on workflow events. They are sent in the background, so a failure never breaks a request.
- **Activity log**: every action is recorded per book and shown in the dashboard.
- **Production basics**: clear HTTP errors (404 / 409 / 422 / 503), a health check, typed API schemas, structured logging, Docker, and a test suite.

## Quick start

```bash
# 1. Install dependencies (Python 3.11+)
python -m pip install -r requirements-dev.txt

# 2. Configure
cp .env.example .env        # then edit DATABASE_URL and an LLM key (or LLM_PROVIDER=mock)

# 3. Create the database tables (safe to re-run; never drops data)
python -m scripts.init_db

# 4. Run
uvicorn backend.main:app --reload --port 8010
```

Then open:

| URL | What |
|-----|------|
| http://localhost:8010 | Dashboard |
| http://localhost:8010/docs | Interactive API docs (Swagger) |
| http://localhost:8010/health | Health check (database + active LLM provider) |

### With Docker

```bash
docker compose up --build
```

This starts PostgreSQL and the API together. Your `.env` supplies the LLM keys, and compiled books are written to `./exports`.

## Configuration

All settings are read from environment variables or `.env` (see [.env.example](.env.example)).

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/postgres` | SQLAlchemy URL. A dedicated database is recommended. |
| `LLM_PROVIDER` | `auto` | `auto`, `openai`, `gemini` or `mock` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4o` | OpenAI credentials and model |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-2.5-flash` | Gemini credentials and model |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `NOTIFY_EMAIL_TO` | | Email notifications (optional) |
| `TEAMS_WEBHOOK_URL` | | MS Teams notifications (optional) |
| `DEFAULT_CHAPTERS` | `10` | Default number of chapters for a new book |
| `DEFAULT_PAGES_PER_CHAPTER` | `20` | Default chapter length in pages |
| `WORDS_PER_PAGE` | `500` | Words per page in the compiled .docx (measured in Word) |
| `SECTION_WORDS` | `1100` | Max words requested per LLM call; sets how many sections a chapter has |
| `MAX_CONCURRENT_JOBS` | `2` | Chapters that can be written at the same time |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed origins |

In `auto` mode the app tries OpenAI first when a key is set, then falls back to Gemini. If every provider fails, the API returns **503** with the provider errors, and nothing is saved.

## Workflow & status gates

Editor decisions use the same `status` values at every gate:

| `status` | Outline | Chapter | Final review |
|----------|---------|---------|--------------|
| `yes` (+ `notes`, required) | Regenerate with notes | Regenerate with notes | Put on hold |
| `no` | Pause | Pause | Pause |
| `no_notes_needed` | Approve → chapters unlocked | Approve → next chapter unlocked | Approve → compile unlocked |

The rules the API enforces (it returns **409 Conflict** if one is broken):

- Chapters require an approved outline. Once any chapter exists, the outline can't be revised.
- Each chapter must be approved before the next one is generated, and only the latest chapter can be regenerated.
- With a real LLM, a 20-page chapter takes about 10–12 model calls, roughly 3–8 minutes depending on the provider.
- Generation stops when the number of chapters in the outline is reached.
- The final review requires every chapter to be approved. Generating or revising a chapter resets the final review.
- Compiling requires an approved final review.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/books/` | Create a book (`title`, `notes_on_outline_before`, optional `target_chapters`, `pages_per_chapter`) and generate its outline |
| `GET` | `/books/` | List books with progress |
| `GET` | `/books/{id}` | Book details: outline versions, chapters, `next_action` |
| `DELETE` | `/books/{id}` | Delete a book and everything belonging to it |
| `GET` | `/books/{id}/logs` | Activity log |
| `POST` | `/books/{id}/outline/generate` | Retry outline generation (e.g. after an LLM outage) |
| `POST` | `/books/{id}/outline-feedback` | Outline decision `{status, notes}` |
| `POST` | `/books/{id}/chapters/generate` | Start writing the next chapter in the background (**202**), or retry a failed one. Poll the chapter's `progress` until the status changes |
| `GET` | `/books/{id}/chapters/{n}` | Chapter content, summary, status, `word_count`, `estimated_pages`, `progress` |
| `POST` | `/books/{id}/chapters/{n}/feedback` | Chapter decision `{status, notes}` |
| `POST` | `/books/{id}/final-review` | Final review decision `{status, notes}` |
| `POST` | `/books/{id}/compile` | Compile to `.docx` |
| `GET` | `/books/{id}/download` | Download the compiled `.docx` |
| `GET` | `/health` | Service health |

Example:

```bash
curl -X POST localhost:8000/books/ -H "Content-Type: application/json" \
  -d '{"title":"The Future of AI Automation","notes_on_outline_before":"Focus on FastAPI, n8n and agents."}'

curl -X POST localhost:8000/books/<id>/outline-feedback -H "Content-Type: application/json" \
  -d '{"status":"no_notes_needed"}'
```

## Project structure

```
backend/
├── main.py                  # App factory: middleware, error handlers, health, dashboard
├── config.py                # Typed settings (pydantic-settings)
├── constants.py             # Workflow status values
├── database.py              # Engine, session dependency, ORM models
├── models.py                # Request/response schemas
├── api/books.py             # REST endpoints
├── services/
│   ├── book_service.py      # Workflow rules and state transitions
│   ├── llm_service.py       # Prompts + OpenAI / Gemini / mock providers
│   └── notification_service.py
├── utils/compiler.py        # Markdown → .docx / .txt
└── static/                  # Dashboard (HTML/CSS/JS, no build step)
database/schema.sql          # Reference SQL schema
scripts/                     # init_db, check_db, check_llm, demo_workflow
tests/                       # pytest suite (SQLite + mock LLM, no network)
```

## Testing & tooling

```bash
python -m pytest                    # full test suite (23 tests): offline, uses SQLite + mock LLM
python -m scripts.check_db          # verify the database connection
python -m scripts.check_llm         # verify the configured LLM provider
python -m scripts.demo_workflow     # run the whole workflow against a running server
python -m scripts.init_db --reset   # drop & recreate this app's tables (destroys data)
```
