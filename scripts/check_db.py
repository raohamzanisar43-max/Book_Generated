"""Verify the database connection and print row counts.  Usage: python -m scripts.check_db"""
import sys

from backend.database import Book, Chapter, Outline, SessionLocal, engine


def main() -> int:
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    try:
        with SessionLocal() as db:
            for model in (Book, Outline, Chapter):
                print(f"  {model.__tablename__:<9} {db.query(model).count()}")
        print("[OK] Database connection successful")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Database connection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
