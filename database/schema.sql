-- Books Table
CREATE TABLE books (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    notes_on_outline_before TEXT,
    outline_status TEXT DEFAULT 'pending', -- pending, generating, review_needed, approved
    final_review_notes_status TEXT DEFAULT 'no', -- yes, no, no_notes_needed
    book_output_status TEXT DEFAULT 'in_progress', -- in_progress, ready, compiled
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Outlines Table
CREATE TABLE outlines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    book_id UUID REFERENCES books(id) ON DELETE CASCADE,
    content TEXT,
    notes_on_outline_after TEXT,
    status TEXT DEFAULT 'review_needed', -- review_needed, approved
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chapters Table
CREATE TABLE chapters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    book_id UUID REFERENCES books(id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    title TEXT,
    content TEXT,
    summary TEXT,
    chapter_notes_status TEXT DEFAULT 'no', -- yes, no, no_notes_needed
    chapter_notes TEXT,
    status TEXT DEFAULT 'pending', -- pending, generating, review_needed, approved
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(book_id, chapter_number)
);

-- Notifications Logs (Optional)
CREATE TABLE logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    book_id UUID REFERENCES books(id),
    message TEXT,
    level TEXT, -- info, error, warning
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
