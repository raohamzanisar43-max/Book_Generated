import asyncio
from backend.database import SessionLocal, Book, settings
from dotenv import load_dotenv
import os

def test_db_connection():
    print("Testing PostgreSQL Connection...")
    print(f"Database URL: {settings.DATABASE_URL}")
    
    try:
        db = SessionLocal()
        # Test connection by querying the books table
        books = db.query(Book).all()
        print("[OK] Database connection successful!")
        print(f"  Books in database: {len(books)}")
        db.close()
        return True
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return False

if __name__ == "__main__":
    load_dotenv()
    test_db_connection()
