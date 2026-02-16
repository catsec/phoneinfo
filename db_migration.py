#!/usr/bin/env python3
"""
Database encryption migration and key rotation.

Automatically migrates database on server startup:
- From unencrypted to encrypted
- From old key to new key (key rotation)

Environment variables:
- DB_ENCRYPTION_KEY: Current (target) encryption key
- DB_ENCRYPTION_KEY_OLD: Previous encryption key
  - If set to "" (empty): old DB is unencrypted
  - If set to "key": old DB is encrypted with that key
  - If not set: no migration needed
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

try:
    from pysqlcipher3 import dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    SQLCIPHER_AVAILABLE = False


def backup_database(db_path):
    """Create timestamped backup of database."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"[Migration] Created backup: {backup_path}")
    return backup_path


def migrate_unencrypted_to_encrypted(old_db_path, new_db_path, new_key):
    """
    Migrate from unencrypted database to encrypted.

    Args:
        old_db_path: Path to unencrypted database
        new_db_path: Path for new encrypted database
        new_key: Encryption key for new database
    """
    print(f"[Migration] Migrating from unencrypted to encrypted...")

    if not SQLCIPHER_AVAILABLE:
        raise RuntimeError("SQLCipher not installed. Cannot encrypt database.")

    # Open unencrypted source
    source = sqlite3.connect(old_db_path)

    # Create encrypted destination
    dest = sqlcipher.connect(new_db_path)
    dest.execute(f"PRAGMA key = '{new_key}'")
    dest.execute("PRAGMA cipher_page_size = 4096")

    # Copy schema and data
    for line in source.iterdump():
        if line not in ('BEGIN;', 'COMMIT;'):
            dest.execute(line)

    dest.commit()
    source.close()
    dest.close()

    print(f"[Migration] Successfully migrated to encrypted database")


def migrate_encrypted_to_encrypted(old_db_path, new_db_path, old_key, new_key):
    """
    Migrate from encrypted database with old key to new key (key rotation).

    Args:
        old_db_path: Path to database encrypted with old key
        new_db_path: Path for database with new key
        old_key: Old encryption key
        new_key: New encryption key
    """
    print(f"[Migration] Rotating encryption key...")

    if not SQLCIPHER_AVAILABLE:
        raise RuntimeError("SQLCipher not installed. Cannot rotate key.")

    # Open with old key
    source = sqlcipher.connect(old_db_path)
    source.execute(f"PRAGMA key = '{old_key}'")
    source.execute("PRAGMA cipher_page_size = 4096")

    # Verify old key works
    try:
        source.execute("SELECT count(*) FROM sqlite_master")
    except Exception as e:
        source.close()
        raise RuntimeError(f"Failed to decrypt with old key: {e}")

    # Create new encrypted database
    dest = sqlcipher.connect(new_db_path)
    dest.execute(f"PRAGMA key = '{new_key}'")
    dest.execute("PRAGMA cipher_page_size = 4096")

    # Copy all data
    for line in source.iterdump():
        if line not in ('BEGIN;', 'COMMIT;'):
            dest.execute(line)

    dest.commit()
    source.close()
    dest.close()

    print(f"[Migration] Successfully rotated encryption key")


def check_and_migrate(db_path):
    """
    Check if database migration is needed and perform it.

    Returns:
        bool: True if migration was performed, False otherwise
    """
    db_path = Path(db_path)
    new_key = os.environ.get('DB_ENCRYPTION_KEY')
    old_key_env = os.environ.get('DB_ENCRYPTION_KEY_OLD')

    # No migration needed if DB_ENCRYPTION_KEY_OLD is not set
    if old_key_env is None:
        return False

    # Check if migration was already done
    migration_marker = db_path.parent / '.db_migration_complete'
    if migration_marker.exists():
        # Check if keys have changed (indicating new rotation request)
        try:
            with open(migration_marker, 'r') as f:
                last_new_key = f.read().strip()
            if last_new_key == new_key:
                # Migration already done with this key
                return False
        except:
            pass

    print("=" * 70)
    print("DATABASE MIGRATION/KEY ROTATION")
    print("=" * 70)

    if not db_path.exists():
        print(f"[Migration] No existing database at {db_path}")
        print(f"[Migration] Will create new encrypted database on first use")
        return False

    # Backup the original database
    backup_path = backup_database(str(db_path))

    try:
        temp_db_path = db_path.parent / f"{db_path.name}.migrating"

        if old_key_env == "":
            # Migrate from unencrypted to encrypted
            print(f"[Migration] Old database is UNENCRYPTED")
            print(f"[Migration] New database will be ENCRYPTED")
            migrate_unencrypted_to_encrypted(str(db_path), str(temp_db_path), new_key)

        else:
            # Rotate encryption key
            print(f"[Migration] Old database is ENCRYPTED")
            print(f"[Migration] Rotating to new encryption key")
            migrate_encrypted_to_encrypted(str(db_path), str(temp_db_path), old_key_env, new_key)

        # Migration successful - replace old database
        old_db_renamed = db_path.parent / f"{db_path.name}.old"
        if old_db_renamed.exists():
            old_db_renamed.unlink()

        db_path.rename(old_db_renamed)
        temp_db_path.rename(db_path)

        print(f"[Migration] Old database renamed to: {old_db_renamed}")
        print(f"[Migration] New database active at: {db_path}")

        # Create migration marker
        with open(migration_marker, 'w') as f:
            f.write(new_key)

        print("=" * 70)
        print("MIGRATION COMPLETE")
        print("=" * 70)
        print()
        print("IMPORTANT:")
        print("  1. Verify the application works correctly")
        print("  2. Remove DB_ENCRYPTION_KEY_OLD from .env")
        print(f"  3. Backup file is at: {backup_path}")
        print(f"  4. Old database is at: {old_db_renamed}")
        print("  5. You can delete old database after verification")
        print()
        print("=" * 70)

        return True

    except Exception as e:
        print(f"[Migration] ERROR: {e}")
        print(f"[Migration] Restoring from backup: {backup_path}")

        # Restore from backup
        if backup_path and Path(backup_path).exists():
            shutil.copy2(backup_path, str(db_path))
            print(f"[Migration] Database restored from backup")

        raise RuntimeError(f"Migration failed: {e}")


if __name__ == "__main__":
    # Test migration
    import sys

    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "db/db.db"

    print(f"Testing migration for: {db_path}")
    print(f"DB_ENCRYPTION_KEY: {'SET' if os.environ.get('DB_ENCRYPTION_KEY') else 'NOT SET'}")
    print(f"DB_ENCRYPTION_KEY_OLD: {os.environ.get('DB_ENCRYPTION_KEY_OLD', 'NOT SET')}")
    print()

    migrated = check_and_migrate(db_path)

    if migrated:
        print("\nMigration test completed successfully!")
    else:
        print("\nNo migration needed.")
