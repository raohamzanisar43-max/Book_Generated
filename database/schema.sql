-- Reference schema for PostgreSQL.
-- The application creates these tables automatically on startup (SQLAlchemy `create_all`)
-- and via `python -m scripts.init_db`; this file documents the structure and can be run
-- manually if you prefer to manage the schema yourself.

CREATE TABLE IF NOT EXISTS books (
    id                        VARCHAR PRIMARY KEY,               -- UUID string
    title                     VARCHAR NOT NULL,
    notes_on_outline_before   TEXT,                              -- required before outline generation
    outline_status            VARCHAR DEFAULT 'pending',         -- pending | generating | review_needed | approved
    final_review_notes_status VARCHAR DEFAULT 'no',              -- yes | no | no_notes_needed
    book_output_status        VARCHAR DEFAULT 'in_progress',     -- in_progress | ready | compiled
    created_at                TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at                TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc')
);

-- Every revision is kept; the newest row is the current outline.
CREATE TABLE IF NOT EXISTS outlines (
    id                     VARCHAR PRIMARY KEY,
    book_id                VARCHAR NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    content                TEXT,
    notes_on_outline_after TEXT,                                 -- editor notes that produced this revision
    status                 VARCHAR DEFAULT 'review_needed',      -- review_needed | approved
    created_at             TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS chapters (
    id                   VARCHAR PRIMARY KEY,
    book_id              VARCHAR NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_number       INTEGER NOT NULL,
    title                VARCHAR,
    content              TEXT,
    summary              TEXT,                                   -- context passed to later chapters
    chapter_notes_status VARCHAR DEFAULT 'no',                   -- yes | no | no_notes_needed
    chapter_notes        TEXT,
    status               VARCHAR DEFAULT 'pending',              -- pending | review_needed | approved
    created_at           TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc'),
    UNIQUE (book_id, chapter_number)
);

-- Workflow activity / audit trail shown in the dashboard.
CREATE TABLE IF NOT EXISTS logs (
    id         VARCHAR PRIMARY KEY,
    book_id    VARCHAR REFERENCES books(id) ON DELETE CASCADE,
    message    TEXT,
    level      VARCHAR,                                          -- info | warning | error
    created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_outlines_book ON outlines (book_id, created_at);
CREATE INDEX IF NOT EXISTS ix_chapters_book ON chapters (book_id, chapter_number);
CREATE INDEX IF NOT EXISTS ix_logs_book     ON logs (book_id, created_at);
