# Setup Guide - Automated Book Generation System

## Complete Tech Stack

| Component | Tool | Version |
|-----------|------|---------|
| **Backend Framework** | FastAPI | Latest |
| **Database** | Supabase (PostgreSQL) | 2.3.1 |
| **AI Model** | OpenAI GPT-4o / Google Gemini | Latest |
| **Output Format** | python-docx | Latest |
| **Notifications** | SMTP (Email) & MS Teams Webhooks | Latest |
| **Python Version** | 3.14+ | |

## Prerequisites

1. Python 3.14 or higher installed
2. Supabase account (free tier works)
3. OpenAI API key or Google Gemini API key
4. (Optional) Gmail account for email notifications
5. (Optional) MS Teams webhook URL

## Step-by-Step Setup

### 1. Install Dependencies

```bash
cd c:\Users\RAO HAMZA\Desktop\Automated_book_generated
python -m pip install -r requirements.txt
```

### 2. Configure Supabase

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Navigate to Project Settings → API
3. Copy your Project URL and anon/public key (or service role key for full access)
4. Open `.env` file and update:
   ```
   SUPABASE_URL=https://your-project-url.supabase.co
   SUPABASE_KEY=your-service-role-key
   ```

### 3. Create Database Tables

1. In Supabase, go to SQL Editor
2. Run the SQL from `database/schema.sql`:
   ```sql
   -- Books Table
   CREATE TABLE books (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       title TEXT NOT NULL,
       notes_on_outline_before TEXT,
       outline_status TEXT DEFAULT 'pending',
       final_review_notes_status TEXT DEFAULT 'no',
       book_output_status TEXT DEFAULT 'in_progress',
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
   );

   -- Outlines Table
   CREATE TABLE outlines (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       book_id UUID REFERENCES books(id) ON DELETE CASCADE,
       content TEXT,
       notes_on_outline_after TEXT,
       status TEXT DEFAULT 'review_needed',
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
       chapter_notes_status TEXT DEFAULT 'no',
       chapter_notes TEXT,
       status TEXT DEFAULT 'pending',
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       UNIQUE(book_id, chapter_number)
   );

   -- Notifications Logs
   CREATE TABLE logs (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       book_id UUID REFERENCES books(id),
       message TEXT,
       level TEXT,
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
   );
   ```

### 4. Configure LLM API

**Option A: OpenAI (Recommended)**
1. Go to [platform.openai.com](https://platform.openai.com)
2. Create an API key
3. Add to `.env`:
   ```
   OPENAI_API_KEY=sk-your-actual-key-here
   ```

**Option B: Google Gemini**
1. Go to [ai.google.dev](https://ai.google.dev)
2. Create an API key
3. Add to `.env`:
   ```
   GEMINI_API_KEY=your-gemini-key-here
   ```

### 5. Configure Notifications (Optional)

**Email (SMTP):**
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
```
*Note: For Gmail, use an App Password, not your regular password*

**MS Teams:**
```
TEAMS_WEBHOOK_URL=https://your-org.webhook.office.com/...
```

### 6. Test Configuration

```bash
# Test database connection
python test_db.py

# Test LLM service
python test_llm.py
```

### 7. Run the Server

```bash
uvicorn backend.main:app --reload
```

The API will be available at `http://localhost:8000`

### 8. Access API Documentation

Open your browser to:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Database Schema

### Books Table
- `id`: UUID (Primary Key)
- `title`: Book title (Required)
- `notes_on_outline_before`: Initial notes before outline generation (Required)
- `outline_status`: pending | generating | review_needed | approved
- `final_review_notes_status`: yes | no | no_notes_needed
- `book_output_status`: in_progress | ready | compiled
- `created_at`, `updated_at`: Timestamps

### Outlines Table
- `id`: UUID (Primary Key)
- `book_id`: Foreign key to books
- `content`: Generated outline content
- `notes_on_outline_after`: Editor notes after review
- `status`: review_needed | approved
- `created_at`: Timestamp

### Chapters Table
- `id`: UUID (Primary Key)
- `book_id`: Foreign key to books
- `chapter_number`: Sequential chapter number
- `title`: Chapter title
- `content`: Generated chapter content
- `summary`: Chapter summary for context chaining
- `chapter_notes_status`: yes | no | no_notes_needed
- `chapter_notes`: Editor notes for chapter
- `status`: pending | generating | review_needed | approved
- `created_at`: Timestamp

### Logs Table
- `id`: UUID (Primary Key)
- `book_id`: Foreign key to books
- `message`: Log message
- `level`: info | error | warning
- `created_at`: Timestamp

## Workflow Status Flow

### Outline Stage
1. `notes_on_outline_before` (required) → triggers outline generation
2. `outline_status`: generating → review_needed
3. Editor provides feedback → status: yes (regenerate) or no_notes_needed (approve)
4. If approved → `outline_status`: approved

### Chapter Stage
1. Generate chapter → `chapter_notes_status`: no
2. Editor reviews → status: yes (needs notes) or no_notes_needed (approve)
3. If yes → provide notes → regenerate chapter
4. If no_notes_needed → `chapter_notes_status`: no_notes_needed, `status`: approved
5. Can now generate next chapter

### Final Compilation
1. All chapters approved → set `final_review_notes_status`: no_notes_needed
2. Compile → generates .docx file in `exports/` folder
3. `book_output_status`: compiled

## Troubleshooting

**Issue: "Invalid API key" for Supabase**
- Verify SUPABASE_URL and SUPABASE_KEY in .env
- Use service role key for full access, or anon key for restricted access

**Issue: OpenAI quota exceeded**
- Check your OpenAI billing at platform.openai.com
- Add credits or switch to Gemini API

**Issue: Module not found errors**
- Run `python -m pip install -r requirements.txt` again
- Ensure you're using Python 3.14+

**Issue: Database connection fails**
- Check Supabase project is active (not paused)
- Verify URL format: https://xxx.supabase.co
- Check API key is correct

## Next Steps

Once setup is complete:
1. Create a book via POST /books/
2. Review and approve outline
3. Generate chapters one by one
4. Approve each chapter
5. Final review and compile to .docx

See README.md for complete API documentation.
