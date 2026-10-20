"""Drive the full workflow against a running server.

Usage:
    uvicorn backend.main:app --port 8010   # in another terminal
    python -m scripts.demo_workflow [--chapters 2] [--base-url http://localhost:8000]
"""
import argparse
import sys
import time

import httpx


def step(name: str) -> None:
    print(f"\n=== {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8010")
    parser.add_argument("--chapters", type=int, default=2)
    args = parser.parse_args()

    approve = {"status": "no_notes_needed", "notes": ""}
    with httpx.Client(base_url=args.base_url, timeout=300) as api:
        def call(method: str, path: str, **kw):
            res = api.request(method, path, **kw)
            if res.is_error:
                print(f"[ERROR] {method} {path} -> {res.status_code}: {res.text}", file=sys.stderr)
                raise SystemExit(1)
            return res.json() if res.content else None

        step("Health")
        print(call("GET", "/health"))

        step("Create book + outline")
        book = call("POST", "/books/", json={
            "title": "The Future of AI Automation",
            "notes_on_outline_before": "Focus on FastAPI, n8n and agentic workflows with practical examples.",
        })
        bid = book["id"]
        print(f"id={bid}  planned chapters={book['chapters_planned']}")
        print(book["outlines"][-1]["content"][:600], "...")

        step("Approve outline")
        print(call("POST", f"/books/{bid}/outline-feedback", json=approve)["message"])

        for n in range(1, args.chapters + 1):
            step(f"Generate + approve chapter {n}")
            call("POST", f"/books/{bid}/chapters/generate")
            last = ""
            while (ch := call("GET", f"/books/{bid}/chapters/{n}"))["status"] == "generating":
                stage = (ch["progress"] or {}).get("stage", "")
                if stage != last:
                    print(f"  ... {stage}")
                    last = stage
                time.sleep(2)
            if ch["status"] == "failed":
                print("[ERROR] chapter generation failed; see GET /books/{id}/logs", file=sys.stderr)
                return 1
            print(f"Chapter {n}: {ch['title']} ({ch['word_count']:,} words, ~{ch['estimated_pages']:.0f} pages)")
            print(call("POST", f"/books/{bid}/chapters/{n}/feedback", json=approve)["message"])

        step("Final review + compile")
        print(call("POST", f"/books/{bid}/final-review", json=approve)["message"])
        result = call("POST", f"/books/{bid}/compile")
        print(f"Saved {result['file_path']}  (download: {args.base_url}{result['download_url']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
