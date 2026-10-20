from backend.services.llm_service import parse_outline_chapters, split_chapter_title
from backend.utils.compiler import safe_filename


def test_parse_outline_chapters_handles_markdown_variants():
    outline = """
    ## Chapters
    **Chapter 1: The Beginning**
    - intro
    ### Chapter 2 - Rising Action
    Chapter 3. Climax
    Chapter 3: Duplicate is ignored
    """
    assert parse_outline_chapters(outline) == [(1, "The Beginning"), (2, "Rising Action"), (3, "Climax")]


def test_split_chapter_title():
    title, body = split_chapter_title("# Chapter 4: The Turn\n\nBody text.", 4)
    assert title == "The Turn"
    assert body == "Body text."


def test_split_chapter_title_falls_back():
    title, body = split_chapter_title("Just prose without a heading.", 2)
    assert title == "Chapter 2"
    assert body == "Just prose without a heading."


def test_safe_filename():
    assert safe_filename('AI: The "Future"/Now?', "docx") == "AI_The_FutureNow.docx"
    assert safe_filename("///", "docx") == "book.docx"


def test_parse_chapter_plan_variants():
    from backend.services.llm_service import parse_chapter_plan

    text = """**TITLE:** Chapter 2: Rising Action
    1. **The Spark** — How it all begins.
    2) Crossing the Line - Stakes rise.
    3. Aftermath: Picking up the pieces.
    """
    title, plan = parse_chapter_plan(text)
    assert title == "Rising Action"
    assert plan == [
        ("The Spark", "How it all begins."),
        ("Crossing the Line", "Stakes rise."),
        ("Aftermath", "Picking up the pieces."),
    ]
