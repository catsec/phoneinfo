import json
import os
import sqlite3
from datetime import datetime, timezone
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
    """Initialize database tables."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Migrate old api_data table to me_data if it exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_data'")
    if cursor.fetchone():
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='me_data'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE api_data RENAME TO me_data")
            conn.commit()

    # Create me_data table (ME API)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS me_data (
            phone_number TEXT PRIMARY KEY DEFAULT '',
            cal_name TEXT DEFAULT '',
            user_email TEXT DEFAULT '',
            user_email_confirmed BOOLEAN DEFAULT FALSE,
            user_profile_picture TEXT DEFAULT '',
            user_first_name TEXT DEFAULT '',
            user_last_name TEXT DEFAULT '',
            user_gender TEXT DEFAULT '',
            user_is_verified BOOLEAN DEFAULT FALSE,
            user_slogan TEXT DEFAULT '',
            social_facebook TEXT DEFAULT '',
            social_twitter TEXT DEFAULT '',
            social_spotify TEXT DEFAULT '',
            social_instagram TEXT DEFAULT '',
            social_linkedin TEXT DEFAULT '',
            social_pinterest TEXT DEFAULT '',
            social_tiktok TEXT DEFAULT '',
            common_name TEXT DEFAULT '',
            me_profile_name TEXT DEFAULT '',
            result_strength TEXT DEFAULT '',
            whitelist TEXT DEFAULT '',
            api_call_time TEXT DEFAULT ''
        )
    """)

    # Create/migrate sync_data table (SYNC API)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_data'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(sync_data)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'first_name' not in columns:
            cursor.execute("DROP TABLE sync_data")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_data (
            phone_number TEXT PRIMARY KEY DEFAULT '',
            cal_name TEXT DEFAULT '',
            name TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            is_potential_spam TEXT DEFAULT '',
            is_business TEXT DEFAULT '',
            job_hint TEXT DEFAULT '',
            company_hint TEXT DEFAULT '',
            website_domain TEXT DEFAULT '',
            company_domain TEXT DEFAULT '',
            api_call_time TEXT DEFAULT ''
        )
    """)

    # Create settings table
    cursor.execute("""
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


def save_to_db(conn, phone_number, cal_name, data, update_time=True):
    """Save data to me_data table (ME API)."""
    cursor = conn.cursor()
    if update_time:
        api_call_time = datetime.now(timezone.utc).isoformat()
    else:
        api_call_time = data.get("api_call_time", datetime.now(timezone.utc).isoformat())
    cursor.execute("""
        INSERT OR REPLACE INTO me_data (
            phone_number, cal_name, user_email, user_email_confirmed, user_profile_picture, user_first_name,
            user_last_name, user_gender, user_is_verified, user_slogan, social_facebook, social_twitter,
            social_spotify, social_instagram, social_linkedin, social_pinterest, social_tiktok, common_name,
            me_profile_name, result_strength, whitelist, api_call_time
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, [
        phone_number,
        cal_name,
        data.get("user_email", ""),
        data.get("user_email_confirmed", ""),
        data.get("user_profile_picture", ""),
        data.get("user_first_name", ""),
        data.get("user_last_name", ""),
        data.get("user_gender", ""),
        data.get("user_is_verified", ""),
        data.get("user_slogan", ""),
        data.get("social_facebook", ""),
        data.get("social_twitter", ""),
        data.get("social_spotify", ""),
        data.get("social_instagram", ""),
        data.get("social_linkedin", ""),
        data.get("social_pinterest", ""),
        data.get("social_tiktok", ""),
        data.get("common_name", ""),
        data.get("me_profile_name", ""),
        data.get("result_strength", ""),
        data.get("whitelist", ""),
        api_call_time
    ])
    conn.commit()


def get_from_db_with_age(conn, phone_number):
    """Get data from me_data table (ME API)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM me_data WHERE phone_number = ?", (phone_number,))
    row = cursor.fetchone()
    if row:
        columns = [column[0] for column in cursor.description]
        record = dict(zip(columns, row))
        return record
    return None


def save_to_sync_db(conn, phone_number, cal_name, data, update_time=True):
    """Save data to sync_data table (SYNC API)."""
    cursor = conn.cursor()
    if update_time:
        api_call_time = datetime.now(timezone.utc).isoformat()
    else:
        api_call_time = data.get("api_call_time", datetime.now(timezone.utc).isoformat())
    cursor.execute("""
        INSERT OR REPLACE INTO sync_data (
            phone_number, cal_name, name, first_name, last_name, is_potential_spam, is_business,
            job_hint, company_hint, website_domain, company_domain, api_call_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        phone_number,
        cal_name,
        data.get("name", ""),
        data.get("first_name", ""),
        data.get("last_name", ""),
        str(data.get("is_potential_spam", "")),
        str(data.get("is_business", "")),
        data.get("job_hint", ""),
        data.get("company_hint", ""),
        data.get("website_domain", ""),
        data.get("company_domain", ""),
        api_call_time
    ])
    conn.commit()


def get_from_sync_db(conn, phone_number):
    """Get data from sync_data table (SYNC API)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sync_data WHERE phone_number = ?", (phone_number,))
    row = cursor.fetchone()
    if row:
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))
    return None


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


# Mapping from flattened ME response keys to DB column names
ME_FLAT_TO_DB = {
    "me.common_name": "common_name",
    "me.profile_name": "me_profile_name",
    "me.result_strength": "result_strength",
    "me.first_name": "user_first_name",
    "me.last_name": "user_last_name",
    "me.email": "user_email",
    "me.email_confirmed": "user_email_confirmed",
    "me.profile_picture": "user_profile_picture",
    "me.gender": "user_gender",
    "me.is_verified": "user_is_verified",
    "me.slogan": "user_slogan",
    "me.social.facebook": "social_facebook",
    "me.social.twitter": "social_twitter",
    "me.social.spotify": "social_spotify",
    "me.social.instagram": "social_instagram",
    "me.social.linkedin": "social_linkedin",
    "me.social.pinterest": "social_pinterest",
    "me.social.tiktok": "social_tiktok",
    "me.whitelist": "whitelist",
}

# Mapping from DB column names to flattened response keys
ME_DB_TO_FLAT = {v: k for k, v in ME_FLAT_TO_DB.items()}
ME_DB_TO_FLAT["api_call_time"] = "me.api_call_time"


def convert_db_to_response(db_result):
    """Convert database record to API response format."""
    response = {
        "phone_number": db_result.get("phone_number", ""),
        "cal_name": db_result.get("cal_name", ""),
    }
    for db_col, flat_key in ME_DB_TO_FLAT.items():
        response[flat_key] = db_result.get(db_col, "")
    return response


def me_flat_to_db_data(flattened_result):
    """Convert flattened ME result to DB column format."""
    return {db_col: flattened_result.get(flat_key, "") for flat_key, db_col in ME_FLAT_TO_DB.items()}


SYNC_SAVE_FIELDS = ["name", "first_name", "last_name", "is_potential_spam",
                     "is_business", "job_hint", "company_hint", "website_domain", "company_domain"]


def sync_flat_to_db_data(sync_flat):
    """Convert flattened SYNC result to DB column format."""
    return {field: sync_flat.get(f"sync.{field}", "") for field in SYNC_SAVE_FIELDS}
