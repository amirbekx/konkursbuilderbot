"""Test database changes: foreign keys, transactions, indexes"""
import sqlite3
import os

db_path = "bot_builder.db"

def test_foreign_keys():
    """Test that foreign keys are enabled"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys")
    fk_status = cursor.fetchone()[0]
    conn.close()
    print(f"✓ Foreign keys: {'ENABLED' if fk_status == 1 else 'DISABLED'}")
    return fk_status == 1

def test_wal_mode():
    """Test that WAL journal mode is enabled"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    conn.close()
    print(f"✓ Journal mode: {mode}")
    return mode.upper() == "WAL"

def test_indexes():
    """Test that new indexes were created"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
    indexes = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    expected_indexes = [
        'idx_users_telegram_id',
        'idx_users_created_at',
        'idx_referrals_bot_referrer',
        'idx_referrals_bot_referred',
        'idx_bot_users_bot_user',
        'idx_required_channels_bot',
        'idx_bots_active',
        'idx_contests_active'
    ]
    
    print(f"✓ Found {len(indexes)} indexes:")
    for idx in indexes:
        status = "✓" if idx in expected_indexes else "?"
        print(f"  {status} {idx}")
    
    missing = set(expected_indexes) - set(indexes)
    if missing:
        print(f"  ✗ Missing: {', '.join(missing)}")
    
    return len(missing) == 0

def test_migration_table():
    """Test that schema_migrations table exists"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    exists = cursor.fetchone() is not None
    
    if exists:
        cursor.execute("SELECT * FROM schema_migrations ORDER BY version")
        migrations = cursor.fetchall()
        print(f"✓ schema_migrations table exists with {len(migrations)} entries:")
        for migration in migrations:
            print(f"  - Version {migration[0]}: {migration[1]} at {migration[2]}")
    else:
        print("✗ schema_migrations table NOT found")
    
    conn.close()
    return exists

def main():
    print("Testing database changes...\n")
    
    if not os.path.exists(db_path):
        print(f"✗ Database not found: {db_path}")
        return
    
    tests = [
        ("Foreign Keys", test_foreign_keys),
        ("WAL Mode", test_wal_mode),
        ("Indexes", test_indexes),
        ("Migration Table", test_migration_table),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{name}:")
        try:
            results.append(test_func())
        except Exception as e:
            print(f"✗ Error: {e}")
            results.append(False)
    
    print("\n" + "="*50)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All database changes verified successfully!")
    else:
        print("✗ Some tests failed")

if __name__ == "__main__":
    main()
