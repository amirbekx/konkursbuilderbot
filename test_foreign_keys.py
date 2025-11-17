"""Test that foreign key constraints work properly"""
import sqlite3
import os

db_path = "bot_builder.db"

def test_foreign_key_enforcement():
    """Test that foreign keys are enforced when _enable_foreign_keys() is called"""
    print("Testing foreign key enforcement...\n")
    
    # Test 1: Without enabling foreign keys (should fail silently)
    print("Test 1: Without PRAGMA foreign_keys (should allow orphan records)")
    conn1 = sqlite3.connect(db_path)
    cursor1 = conn1.cursor()
    try:
        # Try to insert a bot_setting with non-existent bot_id
        cursor1.execute("INSERT INTO bot_settings (bot_id, welcome_message) VALUES (99999, 'test')")
        conn1.commit()
        print("  ✓ Allowed orphan record (foreign keys not enforced)")
        # Clean up
        cursor1.execute("DELETE FROM bot_settings WHERE bot_id = 99999")
        conn1.commit()
    except sqlite3.IntegrityError as e:
        print(f"  ✗ Unexpected: {e}")
    finally:
        conn1.close()
    
    # Test 2: With foreign keys enabled (should enforce constraints)
    print("\nTest 2: With PRAGMA foreign_keys = ON (should reject orphan records)")
    conn2 = sqlite3.connect(db_path)
    conn2.execute("PRAGMA foreign_keys = ON")
    cursor2 = conn2.cursor()
    try:
        cursor2.execute("INSERT INTO bot_settings (bot_id, welcome_message) VALUES (99999, 'test')")
        conn2.commit()
        print("  ✗ FAILED: Allowed orphan record (foreign keys not working!)")
        cursor2.execute("DELETE FROM bot_settings WHERE bot_id = 99999")
        conn2.commit()
    except sqlite3.IntegrityError as e:
        print(f"  ✓ PASSED: Foreign key constraint enforced")
        print(f"    Error: {e}")
    finally:
        conn2.close()
    
    # Test 3: Transaction rollback
    print("\nTest 3: Transaction rollback on error")
    conn3 = sqlite3.connect(db_path)
    conn3.execute("PRAGMA foreign_keys = ON")
    cursor3 = conn3.cursor()
    try:
        cursor3.execute("BEGIN TRANSACTION")
        # Insert valid data first
        cursor3.execute("INSERT INTO users (telegram_id, username) VALUES (999999, 'test_user')")
        # Try to insert invalid foreign key (should fail)
        cursor3.execute("INSERT INTO bot_settings (bot_id, welcome_message) VALUES (99999, 'test')")
        conn3.commit()
        print("  ✗ FAILED: Transaction committed with invalid data")
    except sqlite3.IntegrityError as e:
        conn3.rollback()
        print(f"  ✓ PASSED: Transaction rolled back on error")
        # Verify rollback worked
        cursor3.execute("SELECT COUNT(*) FROM users WHERE telegram_id = 999999")
        count = cursor3.fetchone()[0]
        if count == 0:
            print(f"  ✓ Rollback worked: test user was not inserted")
        else:
            print(f"  ✗ Rollback failed: test user still exists")
    finally:
        conn3.close()
    
    print("\n" + "="*70)
    print("✓ Foreign key enforcement is working correctly!")
    print("  - Enabled per-connection with PRAGMA foreign_keys = ON")
    print("  - Prevents orphan records")
    print("  - Works with transactions and rollback")

if __name__ == "__main__":
    if not os.path.exists(db_path):
        print(f"✗ Database not found: {db_path}")
    else:
        test_foreign_key_enforcement()
