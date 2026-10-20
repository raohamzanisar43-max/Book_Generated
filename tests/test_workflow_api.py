"""End-to-end tests of the human-in-the-loop workflow through the HTTP API."""
import time
from pathlib import Path

from docx import Document

from backend.config import settings


def approve(client, path):
    res = client.post(path, json={"status": "no_notes_needed", "notes": ""})
    assert res.status_code == 200, res.text
    return res.json()


def generate(client, book_id, timeout=30):
    """Start a chapter job and wait for the background writer to finish it."""
    res = client.post(f"/books/{book_id}/chapters/generate")
    assert res.status_code == 202, res.text
    number = res.json()["chapter_number"]
    return wait_for_chapter(client, book_id, number, timeout)


def wait_for_chapter(client, book_id, number, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        chapter = client.get(f"/books/{book_id}/chapters/{number}").json()
        if chapter["status"] != "generating":
            return chapter
        time.sleep(0.05)
    raise AssertionError(f"chapter {number} still generating after {timeout}s")


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"


def test_dashboard_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Book Studio" in res.text


def test_create_book_generates_outline(client, book):
    assert book["outline_status"] == "review_needed"
    assert len(book["outlines"]) == 1
    assert "Chapter 1:" in book["outlines"][0]["content"]
    assert book["chapters_planned"] == 10
    assert book["pages_per_chapter"] == 20
    assert "Review the outline" in book["next_action"]


def test_create_book_requires_notes(client):
    res = client.post("/books/", json={"title": "No notes", "notes_on_outline_before": "   "})
    assert res.status_code == 422


def test_feedback_yes_requires_notes(client, book):
    res = client.post(f"/books/{book['id']}/outline-feedback", json={"status": "yes", "notes": ""})
    assert res.status_code == 422


def test_invalid_status_rejected(client, book):
    res = client.post(f"/books/{book['id']}/outline-feedback", json={"status": "maybe", "notes": ""})
    assert res.status_code == 422


def test_unknown_book_is_404(client):
    assert client.get("/books/does-not-exist").status_code == 404
    assert client.post("/books/does-not-exist/chapters/generate").status_code == 404


def test_custom_book_length(client):
    res = client.post("/books/", json={
        "title": "Short", "notes_on_outline_before": "Brief.", "target_chapters": 3, "pages_per_chapter": 2,
    })
    body = res.json()
    assert body["chapters_planned"] == 3 and body["pages_per_chapter"] == 2
    approve(client, f"/books/{body['id']}/outline-feedback")
    chapter = generate(client, body["id"])
    assert 2 * settings.WORDS_PER_PAGE * 0.9 <= chapter["word_count"] <= 2 * settings.WORDS_PER_PAGE * 1.4


def test_chapter_is_about_twenty_pages(client, book):
    approve(client, f"/books/{book['id']}/outline-feedback")
    chapter = generate(client, book["id"])
    assert chapter["status"] == "review_needed"
    assert 19 <= chapter["estimated_pages"] <= 24
    assert chapter["content"].count("## ") >= 8  # written section by section
    assert chapter["summary"]


def test_outline_revision_creates_new_version(client, book):
    res = client.post(
        f"/books/{book['id']}/outline-feedback",
        json={"status": "yes", "notes": "Add a chapter about ethics."},
    )
    assert res.status_code == 200
    detail = client.get(f"/books/{book['id']}").json()
    assert len(detail["outlines"]) == 2
    assert detail["outlines"][-1]["notes_on_outline_after"] == "Add a chapter about ethics."
    assert detail["outline_status"] == "review_needed"


def test_chapters_blocked_until_outline_approved(client, book):
    res = client.post(f"/books/{book['id']}/chapters/generate")
    assert res.status_code == 409
    assert "outline must be approved" in res.json()["detail"].lower()


def test_next_chapter_blocked_until_previous_approved(client, book):
    bid = book["id"]
    approve(client, f"/books/{bid}/outline-feedback")
    first = generate(client, bid)
    assert first["title"] == "Foundations"  # taken from "Chapter 1: Foundations" in the outline

    second = client.post(f"/books/{bid}/chapters/generate")
    assert second.status_code == 409
    assert "Chapter 1 must be approved" in second.json()["detail"]


def test_chapter_regeneration_with_notes(client, book):
    bid = book["id"]
    approve(client, f"/books/{bid}/outline-feedback")
    generate(client, bid)

    res = client.post(f"/books/{bid}/chapters/1/feedback", json={"status": "yes", "notes": "More examples."})
    assert res.status_code == 200
    chapter = wait_for_chapter(client, bid, 1)
    assert chapter["chapter_notes"] == "More examples."
    assert chapter["status"] == "review_needed"
    assert "More examples." in chapter["content"]


def test_compile_requires_final_review(client, book):
    bid = book["id"]
    approve(client, f"/books/{bid}/outline-feedback")
    generate(client, bid)
    approve(client, f"/books/{bid}/chapters/1/feedback")

    res = client.post(f"/books/{bid}/compile")
    assert res.status_code == 409


def test_final_review_requires_all_chapters_approved(client, book):
    bid = book["id"]
    approve(client, f"/books/{bid}/outline-feedback")
    generate(client, bid)
    res = client.post(f"/books/{bid}/final-review", json={"status": "no_notes_needed", "notes": ""})
    assert res.status_code == 409


def test_full_workflow_compiles_docx(client, book):
    bid = book["id"]
    approve(client, f"/books/{bid}/outline-feedback")

    for n in range(1, 4):
        chapter = generate(client, bid)
        assert chapter["chapter_number"] == n
        approve(client, f"/books/{bid}/chapters/{n}/feedback")

    approve(client, f"/books/{bid}/final-review")
    res = client.post(f"/books/{bid}/compile")
    assert res.status_code == 200, res.text
    path = Path(res.json()["file_path"])
    assert path.exists()

    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "Chapter 1: Foundations" in text
    assert "Chapter 3: Core Principles" in text
    assert "**" not in text and "## " not in text  # markdown was rendered, not copied verbatim

    download = client.get(f"/books/{bid}/download")
    assert download.status_code == 200
    assert download.content[:2] == b"PK"  # .docx is a zip archive

    detail = client.get(f"/books/{bid}").json()
    assert detail["book_output_status"] == "compiled"
    assert len(client.get(f"/books/{bid}/logs").json()) >= 8


def test_new_chapter_resets_final_review(client, book):
    bid = book["id"]
    approve(client, f"/books/{bid}/outline-feedback")
    generate(client, bid)
    approve(client, f"/books/{bid}/chapters/1/feedback")
    approve(client, f"/books/{bid}/final-review")

    generate(client, bid)
    detail = client.get(f"/books/{bid}").json()
    assert detail["final_review_notes_status"] == "no"
    assert detail["book_output_status"] == "in_progress"


def test_delete_book(client, book):
    assert client.delete(f"/books/{book['id']}").status_code == 204
    assert client.get(f"/books/{book['id']}").status_code == 404
