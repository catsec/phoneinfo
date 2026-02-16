import os
import pandas as pd
from datetime import datetime, timezone
from fuzzywuzzy import fuzz

import sqlite3

def apply_final_letter_rules(hebrew_name):
    """Replace the last letter of a Hebrew name with its final form, if applicable."""
    final_letter_map = {
        'כ': 'ך',
        'מ': 'ם',
        'נ': 'ן',
        'פ': 'ף',
        'צ': 'ץ'
    }
    if hebrew_name and hebrew_name[-1] in final_letter_map:
        hebrew_name = hebrew_name[:-1] + final_letter_map[hebrew_name[-1]]
    return hebrew_name

def transliterate_name(word):
    if not word:
        return ''

    # Detect the language of the word
    language = detect_language(word)

    # Handle based on detected language
    if language == "ar":
        # Transliterate Arabic to Hebrew
        return arabic_to_hebrew(word)
    elif language == "en":
        # Transliterate English to Hebrew
        return english_to_hebrew(word)
    elif language == "ru":
        # Transliterate Russian (Cyrillic) to Hebrew
        return russian_to_hebrew(word)
    elif language == "he":
        # Hebrew - return as-is
        return word
    else:
        # Unknown or unsupported, return original
        return word
    
def russian_to_hebrew(name):
    transliteration_map = {
        'А': 'א', 'а': 'א', 'Б': 'ב', 'б': 'ב', 'В': 'ו', 'в': 'ו', 'Г': 'ג', 'г': 'ג',
        'Д': 'ד', 'д': 'ד', 'Е': 'א', 'е': 'א', 'Ё': 'יו', 'ё': 'יו', 'Ж': 'ז', 'ж': 'ז',
        'З': 'ז', 'з': 'ז', 'И': 'י', 'и': 'י', 'Й': 'י', 'й': 'י', 'К': 'ק', 'к': 'ק',
        'Л': 'ל', 'л': 'ל', 'М': 'מ', 'м': 'מ', 'Н': 'נ', 'н': 'נ', 'О': 'ו', 'о': 'ו',
        'П': 'פ', 'п': 'פ', 'Р': 'ר', 'р': 'ר', 'С': 'ס', 'с': 'ס', 'Т': 'ת', 'т': 'ת',
        'У': 'ו', 'у': 'ו', 'Ф': 'פ', 'ф': 'פ', 'Х': 'ח', 'х': 'ח', 'Ц': 'צ', 'ц': 'צ',
        'Ч': 'צ', 'ч': 'צ', 'Ш': 'ש', 'ш': 'ש', 'Щ': 'שצ', 'щ': 'שצ', 'Ъ': '', 'ъ': '',
        'Ы': 'י', 'ы': 'י', 'Ь': '', 'ь': '', 'Э': 'א', 'э': 'א', 'Ю': 'יו', 'ю': 'יו',
        'Я': 'יא', 'я': 'יא', ' ': ' '
    }
    hebrew_name = ''.join(transliteration_map.get(char, '') for char in name)
    return apply_final_letter_rules(hebrew_name)

def arabic_to_hebrew(name):
    transliteration_map = {
        'ا': 'א', 'ب': 'ב', 'ت': 'ת', 'ث': 'ת', 'ج': 'ג', 'ح': 'ח', 'خ': 'ח',
        'د': 'ד', 'ذ': 'ד', 'ر': 'ר', 'ز': 'ז', 'س': 'ס', 'ش': 'ש', 'ص': 'צ',
        'ض': 'צ', 'ط': 'ט', 'ظ': 'ט', 'ع': 'ע', 'غ': 'ע', 'ف': 'פ', 'ق': 'ק',
        'ك': 'כ', 'ل': 'ל', 'م': 'מ', 'ن': 'נ', 'ه': 'ה', 'و': 'ו', 'ي': 'י',
        'ء': 'א', 'أ': 'א', 'إ': 'א', 'ؤ': 'ו', 'ئ': 'א', 'ى': 'א', 'ة': 'ה',
        'آ': 'א', ' ': ' '
    }
    hebrew_name = ''.join(transliteration_map.get(char, '') for char in name)
    return apply_final_letter_rules(hebrew_name)

def load_common_names_json(json_path="names.json"):
    """
    Load structured name mappings from JSON file.

    Returns:
        dict: Flat lookup dict {source_name: hebrew_name} for backward compatibility
        dict: Structured data {hebrew_name: {english: [...], arabic: [...], ...}}
    """
    import json

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            structured_data = json.load(f)

        # Create flat lookup for backward compatibility
        flat_lookup = {}
        for hebrew_name, variants in structured_data.items():
            # Add all variants to flat lookup
            for lang_field in ['english', 'arabic', 'russian', 'russian_cyrillic']:
                variants_list = variants.get(lang_field)
                if variants_list:
                    for variant in variants_list:
                        flat_lookup[variant.lower().strip()] = hebrew_name

        return flat_lookup, structured_data

    except FileNotFoundError:
        return {}, {}

def load_common_names(config_path="names.cfg"):
    """Load common English to Hebrew name mappings from config file (legacy format)."""
    names = {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' not in line:
                    continue
                english, hebrew = line.split(':', 1)
                names[english.strip().lower()] = hebrew.strip()
    except FileNotFoundError:
        pass  # Fall back to transliteration
    return names

# Cache loaded names
_common_names_cache = None
_structured_names_cache = None

def get_common_names():
    """
    Get common names lookup dict, loading from file if needed.
    Prefers names.json, falls back to names.cfg.
    """
    global _common_names_cache, _structured_names_cache

    if _common_names_cache is None:
        # Try JSON first
        flat_lookup, structured_data = load_common_names_json("names.json")

        if flat_lookup:
            _common_names_cache = flat_lookup
            _structured_names_cache = structured_data
        else:
            # Fallback to legacy .cfg format
            _common_names_cache = load_common_names("names.cfg")
            _structured_names_cache = {}

    return _common_names_cache

def get_structured_names():
    """
    Get structured name data organized by Hebrew name.

    Returns:
        dict: {hebrew_name: {english: [...], arabic: [...], russian: [...], russian_cyrillic: [...]}}
    """
    global _structured_names_cache

    if _structured_names_cache is None:
        get_common_names()  # This will populate both caches

    return _structured_names_cache

def get_names_for_db_import():
    """
    Get all names in a database-ready format.

    Returns:
        list: List of dicts ready for database insertion:
              [
                  {
                      'hebrew': 'מוחמד',
                      'english_variants': 'muhammad,mohammed,mohamed',
                      'arabic_variants': 'محمد',
                      'russian_variants': None,
                      'russian_cyrillic_variants': None
                  },
                  ...
              ]
    """
    structured = get_structured_names()

    db_records = []
    for hebrew_name, variants in structured.items():
        record = {
            'hebrew': hebrew_name,
            'english_variants': ','.join(variants['english']) if variants['english'] else None,
            'arabic_variants': ','.join(variants['arabic']) if variants['arabic'] else None,
            'russian_variants': ','.join(variants['russian']) if variants['russian'] else None,
            'russian_cyrillic_variants': ','.join(variants['russian_cyrillic']) if variants['russian_cyrillic'] else None
        }
        db_records.append(record)

    return db_records

def english_to_hebrew(name):
    """
    Transliterate English names to Hebrew.

    Improved handling for:
    - Common name patterns from names.cfg
    - Double consonants (tt, dd, nn, etc.)
    - Vowel combinations
    """
    # Check for common names first (loaded from names.cfg)
    name_lower = name.lower().strip()
    common_names = get_common_names()
    if name_lower in common_names:
        return common_names[name_lower]

    transliteration_map = {
        'a': '', 'b': 'ב', 'c': 'ק', 'd': 'ד', 'e': '', 'f': 'פ', 'g': 'ג', 'h': 'ה',
        'i': 'י', 'j': 'ג׳', 'k': 'ק', 'l': 'ל', 'm': 'מ', 'n': 'נ', 'o': 'ו', 'p': 'פ',
        'q': 'ק', 'r': 'ר', 's': 'ס', 't': 'ת', 'u': 'ו', 'v': 'ו', 'w': 'ו', 'x': 'קס',
        'y': 'י', 'z': 'ז', ' ': ' '
    }
    multi_char_map = {
        'ch': 'ח', 'sh': 'ש', 'th': 'ת', 'kh': 'ח', 'ph': 'פ',
        'oo': 'ו', 'ee': 'י', 'ei': 'יי', 'ie': 'י', 'ou': 'ו',
        'ai': 'יי', 'ay': 'יי', 'ey': 'יי', 'ae': 'יי',
        'ck': 'ק',  # back, jack, etc.
        'tt': 'ת', 'dd': 'ד', 'nn': 'נ', 'mm': 'מ', 'ss': 'ס',  # double consonants
        'll': 'ל', 'rr': 'ר', 'ff': 'פ', 'pp': 'פ', 'bb': 'ב', 'gg': 'ג', 'cc': 'ק',
    }
    hebrew_name = ''
    i = 0
    while i < len(name):
        found = False
        # Check multi-char mappings first (longer patterns first)
        for multi_char in sorted(multi_char_map.keys(), key=len, reverse=True):
            if name[i:i + len(multi_char)].lower() == multi_char:
                hebrew_name += multi_char_map[multi_char]
                i += len(multi_char)
                found = True
                break
        if not found:
            char = name[i].lower()
            if char in {'a', 'e', 'o', 'u'} and i == 0:
                # Initial vowel gets aleph
                hebrew_name += 'א'
            else:
                hebrew_name += transliteration_map.get(char, '')
            i += 1
    if name.lower().endswith('a'):
        if hebrew_name.endswith('א'):
            hebrew_name = hebrew_name[:-1] + 'ה'
        else:
            hebrew_name += 'ה'
    return apply_final_letter_rules(hebrew_name)
   
def detect_language(word):
    # Define Unicode ranges for different languages
    hebrew_range = range(0x0590, 0x05FF + 1)  # Hebrew Unicode range
    arabic_range = range(0x0600, 0x06FF + 1)  # Arabic Unicode range
    english_range = list(range(0x0041, 0x005A + 1)) + list(range(0x0061, 0x007A + 1))  # English (A-Z, a-z)
    russian_range = range(0x0400, 0x04FF + 1)  # Russian (Cyrillic) Unicode range

    # Check the characters in the word
    for char in word:
        code_point = ord(char)
        if code_point in hebrew_range:
            return "he"
        elif code_point in arabic_range:
            return "ar"
        elif code_point in english_range:
            return "en"
        elif code_point in russian_range:
            return "ru"

    return "other"  # Default to 'other' if no matches found


def is_hebrew(text):
    """Check if text contains Hebrew characters."""
    if not text or not text.strip():
        return False
    # Check each word in the text
    for word in text.split():
        if word and detect_language(word) == "he":
            return True
    return False


# Nickname functions - database only

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
    """
    Load nicknames from JSON file into database.
    Only loads if database is empty (seed data).

    Returns:
        int: Number of nicknames loaded, or 0 if database already has data
    """
    import json
    import os

    cursor = conn.cursor()

    # Check if database already has nicknames
    cursor.execute("SELECT COUNT(*) FROM nicknames")
    count = cursor.fetchone()[0]

    if count > 0:
        print(f"[Nicknames] Database already has {count} entries, skipping JSON load")
        return 0

    # Check if JSON file exists
    if not os.path.exists(json_path):
        print(f"[Nicknames] {json_path} not found, skipping seed data load")
        return 0

    # Load from JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            nicknames_data = json.load(f)

        # Insert into database
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
    """
    Given a name (formal or nickname), return all related names.
    Returns a list including the original name and all variants.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT formal_name, all_names FROM nicknames")

    results = set()
    results.add(name)  # Always include the original

    for row in cursor.fetchall():
        formal_name = row[0].strip()
        all_names = [n.strip() for n in row[1].split(',')]

        # Check if name matches the formal_name or is in all_names
        if name == formal_name or name in all_names:
            # Add both the formal_name and all nicknames
            results.add(formal_name)
            results.update(all_names)

    return list(results)

def expand_cal_name_with_nicknames(conn, cal_name):
    """
    Expand a cal_name to include all possible nickname variants.
    Returns tuple: (expanded_string, original_word_count)

    The original_word_count is needed for scoring - we should only
    average the best N matches where N = original words in cal_name.
    """
    words = [w for w in cal_name.split() if len(w) > 1]
    original_count = len(words)
    expanded_parts = []

    for word in words:
        variants = get_all_nicknames_for_name(conn, word)
        expanded_parts.extend(variants)

    return ' '.join(expanded_parts), original_count

def calculate_similarity(text1, text2, original_word_count=None):
    """
    Calculate similarity between expanded cal_name (text1) and me_name (text2).

    Algorithm:
    1. Check for superset match (one contains all words of the other) → 95-100
    2. Otherwise combine: token_set_ratio (50%) + word matching (30%) + exact bonus (20%)

    Args:
        text1: Expanded cal_name with nickname variants
        text2: me_name + me_translated combined
        original_word_count: Number of original words in cal_name
    """
    if not text1 or not text2:
        return 0

    # Split into words, filter short words
    words1 = [word for word in text1.split() if len(word) > 1]
    words2 = [word for word in text2.split() if len(word) > 1]

    if not words1 or not words2:
        return 0

    words1_set = set(words1)
    words2_set = set(words2)

    # Quick check: if enough original words have exact matches, return 100%
    # This handles nickname expansion where extra variants don't match but originals do
    if original_word_count:
        exact_matches = sum(1 for w in words1_set if w in words2_set)
        if exact_matches >= original_word_count:
            return 100

    # Check for superset relationship (handles maiden names, titles, etc.)
    # If all words from me_name are in cal_name (or vice versa), it's likely the same person
    def check_superset_match(smaller_set, larger_set):
        """Check if all words from smaller set have a match in larger set."""
        matched = 0
        for word in smaller_set:
            # Check for exact match or high fuzzy match (>85)
            if word in larger_set:
                matched += 1
            else:
                # Check fuzzy match for slight variations
                best = max((fuzz.ratio(word, w) for w in larger_set), default=0)
                if best >= 85:
                    matched += 1
        return matched == len(smaller_set)

    # me_name is subset of cal_name (e.g., "אפרת מנדל" in "אפרת חשן מנדל")
    if check_superset_match(words2_set, words1_set):
        # All me_name words found in cal_name - very high confidence
        # Score based on how much of cal_name is covered
        coverage = len(words2_set) / original_word_count if original_word_count else 1
        return int(95 + (coverage * 5))  # 95-100

    # cal_name is subset of me_name (e.g., cal has "דוד" but me has "דוד כהן")
    if check_superset_match(words1_set, words2_set):
        # All cal_name words found in me_name
        # Score based on how complete the original input was vs API result
        # If user provided full name and all words match → 100%
        if original_word_count:
            # Check how many of the API's core words we matched
            # If we matched at least as many words as we input, it's a full match
            matched_in_api = sum(1 for w in words1_set if w in words2_set)
            if matched_in_api >= original_word_count:
                return 100
        coverage = len(words1_set) / len(words2_set)
        return int(90 + (coverage * 10))  # 90-100

    # Standard matching for non-superset cases
    # Component 1: token_set_ratio (handles word order, partial matches)
    token_score = fuzz.token_set_ratio(text1, text2)

    # Component 2: Word-level best matches
    best_matches = []
    for word1 in words1:
        best_score = max((fuzz.ratio(word1, w2) for w2 in words2), default=0)
        best_matches.append(best_score)

    best_matches.sort(reverse=True)
    n = min(len(best_matches), original_word_count if original_word_count else 2)
    word_score = sum(best_matches[:n]) / n if n > 0 else 0

    # Component 3: Exact match bonus
    exact_matches = sum(1 for w in words1 if w in words2_set)
    exact_ratio = exact_matches / original_word_count if original_word_count else 0
    exact_score = min(100, exact_ratio * 100)

    # Combine scores
    final_score = (token_score * 0.5) + (word_score * 0.3) + (exact_score * 0.2)

    return int(final_score)

def validate_phone_numbers(phone_numbers):
    for phone in phone_numbers:
        if not str(phone).isdigit() or not str(phone).startswith("972") or len(str(phone)) != 12:
            return False
    return True

def convert_to_international(phone_numbers):
    converted_numbers = []
    for phone in phone_numbers:
        phone_str = str(phone).strip()
        if len(phone_str) == 10 and phone_str.startswith("0"):
            phone_str = "972" + phone_str[1:]
        converted_numbers.append(phone_str)
    return converted_numbers

def init_db(db_name):
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
    # Check if table needs migration (old schema had cal_name instead of name/first_name/etc)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_data'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(sync_data)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'first_name' not in columns:
            # Old schema - drop and recreate
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

    # Create users table (authentication)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            seed TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            failed_login_counter INTEGER DEFAULT 0,
            last_login_datetime TEXT DEFAULT '',
            email TEXT DEFAULT '',
            admin_flag INTEGER DEFAULT 0,
            active_flag INTEGER DEFAULT 1
        )
    """)

    # Create settings table (application configuration)
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


def count_users(conn):
    """Return total number of users."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def create_user(conn, username, seed, hashed_password, email="", admin_flag=0, active_flag=1):
    """Create a user record."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (
            username, seed, hashed_password, failed_login_counter,
            last_login_datetime, email, admin_flag, active_flag
        ) VALUES (?, ?, ?, 0, '', ?, ?, ?)
        """,
        (username, seed, hashed_password, email, int(admin_flag), int(active_flag)),
    )
    conn.commit()


def delete_user(conn, username):
    """Delete a user record."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    return cursor.rowcount > 0


def get_user_by_username(conn, username):
    """Get user by username (normalized lowercase key expected)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT username, seed, hashed_password, failed_login_counter,
               last_login_datetime, email, admin_flag, active_flag
        FROM users
        WHERE username = ?
        """,
        (username,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def list_users(conn):
    """List all users for management screen."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT username, failed_login_counter, last_login_datetime,
               email, admin_flag, active_flag
        FROM users
        ORDER BY username
        """
    )
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def increment_failed_login(conn, username):
    """Increment failed login counter for a user."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET failed_login_counter = failed_login_counter + 1 WHERE username = ?",
        (username,),
    )
    conn.commit()


def reset_failed_login_counter(conn, username):
    """Reset failed login counter to zero."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET failed_login_counter = 0 WHERE username = ?",
        (username,),
    )
    conn.commit()


def update_last_login_datetime(conn, username, login_time_iso):
    """Update last login date/time for a user."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET last_login_datetime = ? WHERE username = ?",
        (login_time_iso, username),
    )
    conn.commit()


def update_user_flags(conn, username, admin_flag=None, active_flag=None):
    """Update admin/active flags for a user."""
    updates = []
    params = []

    if admin_flag is not None:
        updates.append("admin_flag = ?")
        params.append(int(admin_flag))
    if active_flag is not None:
        updates.append("active_flag = ?")
        params.append(int(active_flag))

    if not updates:
        return

    params.append(username)
    sql = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()


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


# SYNC API database functions

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
    if isinstance(data, dict):
        return {key: clean_data_for_db(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [clean_data_for_db(item) for item in data]
    elif data is None:
        return ""
    else:
        return data
