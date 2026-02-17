"""Generic database operations.

Provider-specific DB operations (table creation, cache get/save) live in
each provider class under providers/.
"""

import json
import os
import sqlite3
from flask import g
from config import DATABASE


def get_db():
    """Get database connection for current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, timeout=10)
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=5000")
    return g.db


def init_db(db_name):
    """Initialize database: provider tables + common tables.

    Provider tables are created by each provider's init_table() method.
    This function creates common tables (settings, nicknames).
    """
    from providers import get_all_providers

    conn = sqlite3.connect(db_name)

    # Let each provider create/migrate its own table
    for provider in get_all_providers():
        provider.init_table(conn)

    # Settings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def init_nickname_table(conn):
    """Create the nickname table if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nicknames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            formal_name TEXT NOT NULL,
            all_names TEXT NOT NULL
        )
    """)
    conn.commit()


def load_nicknames_from_json(conn, json_path="nicknames.json"):
    """Load nicknames from JSON file into database (seed data, only if empty)."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM nicknames")
    count = cursor.fetchone()[0]

    if count > 0:
        print(f"[Nicknames] Database already has {count} entries, skipping JSON load")
        return 0

    if not os.path.exists(json_path):
        print(f"[Nicknames] {json_path} not found, skipping seed data load")
        return 0

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            nicknames_data = json.load(f)

        for entry in nicknames_data:
            cursor.execute(
                "INSERT INTO nicknames (formal_name, all_names) VALUES (?, ?)",
                (entry['formal_name'], entry['all_names'])
            )

        conn.commit()
        print(f"[Nicknames] Loaded {len(nicknames_data)} entries from {json_path}")
        return len(nicknames_data)

    except Exception as e:
        print(f"[Nicknames] Error loading from JSON: {e}")
        conn.rollback()
        return 0


def get_all_nicknames_for_name(conn, name):
    """Given a name (formal or nickname), return all related names."""
    cursor = conn.cursor()
    cursor.execute("SELECT formal_name, all_names FROM nicknames")

    results = set()
    results.add(name)

    for row in cursor.fetchall():
        formal_name = row[0].strip()
        all_names = [n.strip() for n in row[1].split(',')]

        if name == formal_name or name in all_names:
            results.add(formal_name)
            results.update(all_names)

    return list(results)


def get_setting(conn, key, default=None):
    """Get a setting value from the settings table."""
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else default


def set_setting(conn, key, value):
    """Set a setting value in the settings table."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (key, value))
    conn.commit()


def clean_data_for_db(data):
    """Recursively replace None values with empty strings."""
    if isinstance(data, dict):
        return {key: clean_data_for_db(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [clean_data_for_db(item) for item in data]
    elif data is None:
        return ""
    else:
        return data
