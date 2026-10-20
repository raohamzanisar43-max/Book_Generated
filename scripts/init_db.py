"""Create database tables (idempotent).

Usage:
    python -m scripts.init_db          # create any missing tables, keep data
    python -m scripts.init_db --reset  # DROP all tables and recreate (destroys data!)
"""
import argparse
import sys

from sqlalchemy import inspect, text

from backend.database import Base, create_tables, engine, settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop all tables first (destroys all data)")
    args = parser.parse_args()

    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "postgresql":
                print(f"[OK] Connected: {conn.execute(text('SELECT version()')).scalar()[:60]}")
            else:
                print(f"[OK] Connected ({engine.dialect.name})")

        if args.reset:
            print("Dropping existing tables...")
            Base.metadata.drop_all(bind=engine)

        create_tables()
        print(f"[OK] Tables: {', '.join(sorted(inspect(engine).get_table_names()))}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Database initialisation failed: {exc}", file=sys.stderr)
        print(f"        Check DATABASE_URL in .env (currently set for {settings.DATABASE_URL.split('@')[-1]})",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
