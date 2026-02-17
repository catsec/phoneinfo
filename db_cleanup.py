#!/usr/bin/env python3
"""
Database cleanup script:
1. Drop name_mappings table (no longer used - we use names.json)
2. Sanitize all string fields in existing tables
"""

import sqlite3
from input_validator import clean_name, clean_email, clean_phone, sanitize_string

DB_PATH = 'db/db.db'

def cleanup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("[Cleanup] Starting database cleanup...")

    # 1. Drop name_mappings table
    print("[Cleanup] Dropping name_mappings table...")
    cursor.execute("DROP TABLE IF EXISTS name_mappings")
    conn.commit()
    print("[Cleanup] OK - name_mappings table dropped")

    # 2. Sanitize nicknames table
    print("[Cleanup] Sanitizing nicknames table...")
    cursor.execute("SELECT id, formal_name, all_names FROM nicknames")
    nicknames = cursor.fetchall()

    for row in nicknames:
        id_val, formal_name, all_names = row

        # Sanitize formal_name
        clean_formal = sanitize_string(formal_name, max_length=200, field_type='name')

        # Sanitize all_names (comma-separated)
        if all_names:
            names_list = [sanitize_string(n.strip(), max_length=100, field_type='name')
                         for n in all_names.split(',')]
            names_list = [n for n in names_list if n]  # Remove empty
            clean_all_names = ','.join(names_list) if names_list else ''
        else:
            clean_all_names = ''

        # Update if changed
        if clean_formal != formal_name or clean_all_names != all_names:
            cursor.execute(
                "UPDATE nicknames SET formal_name = ?, all_names = ? WHERE id = ?",
                (clean_formal, clean_all_names, id_val)
            )

    conn.commit()
    print(f"[Cleanup] OK - Sanitized {len(nicknames)} nicknames")

    # 3. Sanitize me_data table
    print("[Cleanup] Sanitizing me_data table...")
    cursor.execute("""
        SELECT phone_number, user_email, user_first_name, user_last_name,
               common_name, me_profile_name, cal_name
        FROM me_data
    """)
    me_rows = cursor.fetchall()

    for row in me_rows:
        phone, email, first, last, common, profile, cal = row

        # Sanitize fields
        clean_phone_val = clean_phone(phone) if phone else ''
        clean_email_val = sanitize_string(email, max_length=200, field_type='email') if email else ''
        clean_first = sanitize_string(first, max_length=100, field_type='name') if first else ''
        clean_last = sanitize_string(last, max_length=100, field_type='name') if last else ''
        clean_common = sanitize_string(common, max_length=200, field_type='name') if common else ''
        clean_profile = sanitize_string(profile, max_length=200, field_type='name') if profile else ''
        clean_cal = sanitize_string(cal, max_length=200, field_type='name') if cal else ''

        # Update if any changed
        if (clean_phone_val != phone or clean_email_val != email or
            clean_first != first or clean_last != last or
            clean_common != common or clean_profile != profile or clean_cal != cal):
            cursor.execute("""
                UPDATE me_data
                SET phone_number = ?, user_email = ?, user_first_name = ?, user_last_name = ?,
                    common_name = ?, me_profile_name = ?, cal_name = ?
                WHERE phone_number = ?
            """, (clean_phone_val, clean_email_val, clean_first, clean_last,
                  clean_common, clean_profile, clean_cal, phone))

    conn.commit()
    print(f"[Cleanup] OK - Sanitized {len(me_rows)} me_data rows")

    # 4. Sanitize sync_data table
    print("[Cleanup] Sanitizing sync_data table...")
    cursor.execute("""
        SELECT phone_number, cal_name, name, first_name, last_name
        FROM sync_data
    """)
    sync_rows = cursor.fetchall()

    for row in sync_rows:
        phone, cal_name, name, first_name, last_name = row

        # Sanitize fields
        clean_phone_val = clean_phone(phone) if phone else ''
        clean_cal = sanitize_string(cal_name, max_length=200, field_type='name') if cal_name else ''
        clean_name = sanitize_string(name, max_length=200, field_type='name') if name else ''
        clean_first = sanitize_string(first_name, max_length=100, field_type='name') if first_name else ''
        clean_last = sanitize_string(last_name, max_length=100, field_type='name') if last_name else ''

        # Update if any changed
        if (clean_phone_val != phone or clean_cal != cal_name or
            clean_name != name or clean_first != first_name or clean_last != last_name):
            cursor.execute("""
                UPDATE sync_data
                SET phone_number = ?, cal_name = ?, name = ?, first_name = ?, last_name = ?
                WHERE phone_number = ?
            """, (clean_phone_val, clean_cal, clean_name, clean_first, clean_last, phone))

    conn.commit()
    print(f"[Cleanup] OK - Sanitized {len(sync_rows)} sync_data rows")

    # 5. Sanitize users table
    print("[Cleanup] Sanitizing users table...")
    cursor.execute("SELECT username, email FROM users")
    user_rows = cursor.fetchall()

    for row in user_rows:
        username, email = row

        # Username should be alphanumeric + specific chars (already validated on creation)
        # Email should be sanitized
        clean_email_val = sanitize_string(email, max_length=200, field_type='email') if email else ''

        # Update if changed
        if clean_email_val != email:
            cursor.execute(
                "UPDATE users SET email = ? WHERE username = ?",
                (clean_email_val, username)
            )

    conn.commit()
    print(f"[Cleanup] OK - Sanitized {len(user_rows)} users")

    # 6. Show final table summary
    print("\n[Cleanup] Final database state:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) FROM {table[0]}')
        count = cursor.fetchone()[0]
        print(f"  OK - {table[0]}: {count} rows")

    conn.close()
    print("\n[Cleanup] Database cleanup complete! [DONE]")

if __name__ == '__main__':
    cleanup_database()
