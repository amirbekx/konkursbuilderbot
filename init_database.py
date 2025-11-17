"""Initialize database with new changes"""
import sys
sys.path.insert(0, '.')

from database import Database

def main():
    print("Initializing database with new schema...")
    db = Database()
    print("✓ Database initialized successfully!")
    print("\nDatabase file:", db.db_path)
    
    # Verify changes
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    # Check foreign keys
    cursor.execute("PRAGMA foreign_keys")
    fk_status = cursor.fetchone()[0]
    print(f"Foreign keys: {'ENABLED' if fk_status == 1 else 'DISABLED'}")
    
    # Check journal mode
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    print(f"Journal mode: {mode}")
    
    # Check indexes
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
    idx_count = cursor.fetchone()[0]
    print(f"Indexes created: {idx_count}")
    
    # Check schema_migrations
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    has_migrations = cursor.fetchone() is not None
    print(f"Schema migrations table: {'EXISTS' if has_migrations else 'NOT FOUND'}")
    
    conn.close()

if __name__ == "__main__":
    main()
