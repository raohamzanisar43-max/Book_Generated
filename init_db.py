"""
Initialize database tables and test connection
"""
from backend.database import engine, create_tables, settings, Base
from sqlalchemy import text

def init_database():
    print("Initializing database...")
    print(f"Database URL: {settings.DATABASE_URL}")
    
    try:
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print("[OK] Connected to PostgreSQL")
            print(f"  Version: {version[:50]}...")
        
        # Drop existing tables if they exist
        print("\nDropping existing tables...")
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS logs CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS chapters CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS outlines CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS books CASCADE"))
            conn.commit()
        print("[OK] Existing tables dropped")
        
        # Create tables
        print("\nCreating tables...")
        create_tables()
        print("[OK] Tables created successfully")
        
        # Verify tables
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            tables = [row[0] for row in result.fetchall()]
            print(f"[OK] Tables in database: {', '.join(tables)}")
        
        print("\n[SUCCESS] Database initialization complete!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    init_database()
