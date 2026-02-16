import os
import sqlite3
import uuid
import tempfile
import re
import secrets
import pandas as pd
import threading
import time
from flask import Flask, request, jsonify, g, render_template, send_file, session, redirect, url_for
from werkzeug.utils import secure_filename
from datetime import datetime, timezone, timedelta
from functools import wraps
from dotenv import load_dotenv
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functions import (
    init_db,
    init_nickname_table,
    load_nicknames_from_json,
    save_to_db,
    get_from_db_with_age,
    save_to_sync_db,
    get_from_sync_db,
    transliterate_name,
    is_hebrew,
    get_all_nicknames_for_name,
    clean_data_for_db,
    validate_phone_numbers,
    convert_to_international,
    count_users,
    create_user,
    get_user_by_username,
    list_users,
    increment_failed_login,
    reset_failed_login_counter,
    update_last_login_datetime,
    update_user_flags,
    get_setting,
    set_setting,
)
from scoring import ScoreEngine
from api_me import call_api as me_call_api, flatten_user_data as me_flatten_user_data
from api_sync import call_api as sync_call_api, flatten_user_data as sync_flatten_user_data
from input_validator import validate_nicknames_data, validate_phone_data, validate_file_size, ValidationError

# Load .env file
load_dotenv()

# Store processed files temporarily
PROCESSED_FILES = {}

# File cleanup configuration
FILE_EXPIRY_HOURS = 1  # Files older than 1 hour will be deleted
CLEANUP_INTERVAL_MINUTES = 10  # Run cleanup every 10 minutes

def cleanup_old_files():
    """Background task to clean up old processed files."""
    while True:
        try:
            time.sleep(CLEANUP_INTERVAL_MINUTES * 60)  # Sleep first, then clean

            now = datetime.now()
            expired_files = []

            # Find expired files
            for file_id, file_info in PROCESSED_FILES.items():
                created_time = file_info.get("created")
                if created_time and (now - created_time) > timedelta(hours=FILE_EXPIRY_HOURS):
                    expired_files.append(file_id)

            # Remove expired files
            for file_id in expired_files:
                file_info = PROCESSED_FILES.pop(file_id, None)
                if file_info:
                    file_path = file_info.get("path")
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            print(f"Cleaned up expired file: {file_id}")
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")

            if expired_files:
                print(f"Cleanup: Removed {len(expired_files)} expired file(s)")

        except Exception as e:
            print(f"Error in cleanup task: {e}")

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

app = Flask("phoneinfo")

# Session cookie security configuration
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to session cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection

# Enable HTTPS-only cookies in production (Cloudflare Tunnel provides HTTPS)
if os.environ.get('PRODUCTION', '').lower() == 'true':
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS-only cookies

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._@-]{0,63}$")
SPECIAL_PATTERN = re.compile(r"[^A-Za-z0-9]")
password_hasher = PasswordHasher()

# File upload security
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_env_value(env_var, required=True, default=""):
    """Get config value from environment variable."""
    value = os.environ.get(env_var, "").strip()
    if value:
        return value
    if required:
        raise RuntimeError(
            f"Missing configuration: set {env_var} environment variable in .env file"
        )
    return default


# API Configuration from environment variables
API_URL = get_env_value("ME_API_URL")
SID = get_env_value("ME_API_SID")
TOKEN = get_env_value("ME_API_TOKEN")

# SYNC API Configuration
SYNC_API_URL = get_env_value("SYNC_API_URL", required=False)
SYNC_API_TOKEN = get_env_value("SYNC_API_TOKEN", required=False)

# Database configuration
DATABASE = os.environ.get("DATABASE", "db/db.db")

# Server configuration
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", "5001"))

# Check if database migration/key rotation is needed
from db_migration import check_and_migrate
try:
    migration_performed = check_and_migrate(DATABASE)
    if migration_performed:
        print("[Server] Database migration completed. Continuing startup...")
except Exception as e:
    print(f"[Server] CRITICAL: Database migration failed: {e}")
    print("[Server] Server startup aborted. Fix the issue and restart.")
    import sys
    sys.exit(1)

# Initialize database on startup
_init_conn = init_db(DATABASE)
init_nickname_table(_init_conn)
load_nicknames_from_json(_init_conn)  # Load seed data if database is empty

# Names are loaded from names.json on first use (see functions.py)

# Initialize SECRET_KEY (env variable > database > generate new)
if os.environ.get("SECRET_KEY"):
    # Use environment variable if set (highest priority)
    app.secret_key = os.environ.get("SECRET_KEY")
else:
    # Try to get from database
    secret_key = get_setting(_init_conn, "SECRET_KEY")
    if not secret_key:
        # Generate new secret key and store it
        secret_key = secrets.token_hex(32)
        set_setting(_init_conn, "SECRET_KEY", secret_key)
        print(f"Generated and stored new SECRET_KEY in database")
    app.secret_key = secret_key

_init_conn.close()


# Security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'

    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # Enable XSS filter (legacy browsers)
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # Control referrer information
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Prevent caching of sensitive pages
    if request.path.startswith('/web/') and request.path != '/web/login':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response


def get_db():
    """Get database connection for current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
    return g.db


def is_api_request_path(path):
    return not path.startswith("/web") and path not in ["/"]


def normalize_username(username):
    return (username or "").strip().lower()


def is_valid_username(username):
    candidate = (username or "").strip()
    if len(candidate) < 1 or len(candidate) > 64:
        return False
    return bool(USERNAME_PATTERN.fullmatch(candidate))


def is_valid_password(password):
    if not password or len(password) < 8:
        return False
    categories = 0
    if re.search(r"[a-z]", password):
        categories += 1
    if re.search(r"[A-Z]", password):
        categories += 1
    if re.search(r"[0-9]", password):
        categories += 1
    if SPECIAL_PATTERN.search(password):
        categories += 1
    return categories >= 3


def hash_password_with_seed(password, seed):
    return password_hasher.hash(f"{password}{seed}")


def verify_password_with_seed(password, seed, hashed_password):
    try:
        return password_hasher.verify(hashed_password, f"{password}{seed}")
    except (VerifyMismatchError, VerificationError):
        return False


def get_logged_in_user():
    username = session.get("username")
    if not username:
        return None
    return get_user_by_username(get_db(), normalize_username(username))


def require_admin(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = get_logged_in_user()
        if not user:
            return redirect(url_for("web_login_page"))
        if int(user.get("admin_flag", 0)) != 1:
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return view_func(*args, **kwargs)

    return wrapper


@app.before_request
def enforce_authentication_flow():
    endpoint = request.endpoint or ""

    exempt_endpoints = {
        "static",
        "health",
        "web_login_page",
        "web_login",
        "web_logout",
        "web_user_bootstrap_page",
        "web_user_bootstrap_create",
    }

    if endpoint in exempt_endpoints:
        return None

    user_total = count_users(get_db())
    path = request.path or ""

    if user_total == 0:
        # First run: skip login and force user bootstrap page.
        if endpoint not in {"web_user_bootstrap_page", "web_user_bootstrap_create", "health", "static"}:
            if is_api_request_path(path):
                return jsonify({"error": "No users configured. Complete first-run bootstrap at /web/users/bootstrap"}), 503
            return redirect(url_for("web_user_bootstrap_page"))
        return None

    user = get_logged_in_user()
    if not user:
        if is_api_request_path(path):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("web_login_page"))

    if int(user.get("active_flag", 1)) != 1:
        session.clear()
        if is_api_request_path(path):
            return jsonify({"error": "User inactive"}), 403
        return redirect(url_for("web_login_page"))

    return None


@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def convert_db_to_response(db_result):
    """Convert database record to API response format."""
    return {
        "phone_number": db_result.get("phone_number", ""),
        "cal_name": db_result.get("cal_name", ""),
        "me.common_name": db_result.get("common_name", ""),
        "me.profile_name": db_result.get("me_profile_name", ""),
        "me.result_strength": db_result.get("result_strength", ""),
        "me.first_name": db_result.get("user_first_name", ""),
        "me.last_name": db_result.get("user_last_name", ""),
        "me.email": db_result.get("user_email", ""),
        "me.email_confirmed": db_result.get("user_email_confirmed", ""),
        "me.profile_picture": db_result.get("user_profile_picture", ""),
        "me.gender": db_result.get("user_gender", ""),
        "me.is_verified": db_result.get("user_is_verified", ""),
        "me.slogan": db_result.get("user_slogan", ""),
        "me.social.facebook": db_result.get("social_facebook", ""),
        "me.social.twitter": db_result.get("social_twitter", ""),
        "me.social.spotify": db_result.get("social_spotify", ""),
        "me.social.instagram": db_result.get("social_instagram", ""),
        "me.social.linkedin": db_result.get("social_linkedin", ""),
        "me.social.pinterest": db_result.get("social_pinterest", ""),
        "me.social.tiktok": db_result.get("social_tiktok", ""),
        "me.whitelist": db_result.get("whitelist", ""),
        "me.api_call_time": db_result.get("api_call_time", ""),
    }


@app.route("/me", methods=["POST"])
def me_api():
    """
    ME API wrapper - checks cache, calls external API if needed, stores in DB.

    Input: {
        "phone": "972...",
        "cal_name": "...",
        "use_cache": true,      # optional, default true - check cache first
        "refresh_days": 7,      # optional - refresh if data older than N days (0 = always refresh)
        "noapi": false          # optional, default false - if true, only use cache
    }
    Output: { "phone_number": "...", "common_name": "...", ..., "from_cache": bool }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    phone = data.get("phone")
    cal_name = data.get("cal_name", "")
    use_cache = data.get("use_cache", True)
    refresh_days = data.get("refresh_days")
    noapi = data.get("noapi", False)

    if not phone:
        return jsonify({"error": "phone is required"}), 400

    try:
        db = get_db()

        # Check cache first if enabled
        if use_cache:
            db_result = get_from_db_with_age(db, phone)
            if db_result:
                # Update cal_name if different
                if db_result.get("cal_name") != cal_name:
                    db_result["cal_name"] = cal_name
                    save_to_db(db, phone, cal_name, db_result, update_time=False)

                # Check if refresh is needed
                needs_refresh = False
                if refresh_days is not None:
                    if refresh_days == 0:
                        needs_refresh = True
                    else:
                        api_call_time = datetime.fromisoformat(db_result.get("api_call_time", ""))
                        if api_call_time.tzinfo is None:
                            api_call_time = api_call_time.replace(tzinfo=timezone.utc)
                        age_days = (datetime.now(timezone.utc) - api_call_time).days
                        needs_refresh = age_days >= refresh_days

                if not needs_refresh:
                    result = convert_db_to_response(db_result)
                    result["from_cache"] = True
                    return jsonify(result)

        # If noapi mode, return empty result or cached data
        if noapi:
            if use_cache and db_result:
                result = convert_db_to_response(db_result)
                result["from_cache"] = True
                return jsonify(result)
            else:
                result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
                result["phone_number"] = phone
                result["cal_name"] = cal_name
                result["me.common_name"] = "NOT IN CACHE"
                result["from_cache"] = False
                return jsonify(result)

        # Call the ME API
        api_result = me_call_api(phone, API_URL, SID, TOKEN)

        if api_result is None:
            flattened_result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
        else:
            flattened_result = clean_data_for_db(me_flatten_user_data(api_result, prefix="me"))

        # Add metadata
        flattened_result["phone_number"] = phone
        flattened_result["cal_name"] = cal_name
        flattened_result["me.api_call_time"] = datetime.now(timezone.utc).isoformat()

        # Convert to DB format and save
        db_data = {
            "common_name": flattened_result.get("me.common_name", ""),
            "me_profile_name": flattened_result.get("me.profile_name", ""),
            "result_strength": flattened_result.get("me.result_strength", ""),
            "user_first_name": flattened_result.get("me.first_name", ""),
            "user_last_name": flattened_result.get("me.last_name", ""),
            "user_email": flattened_result.get("me.email", ""),
            "user_email_confirmed": flattened_result.get("me.email_confirmed", ""),
            "user_profile_picture": flattened_result.get("me.profile_picture", ""),
            "user_gender": flattened_result.get("me.gender", ""),
            "user_is_verified": flattened_result.get("me.is_verified", ""),
            "user_slogan": flattened_result.get("me.slogan", ""),
            "social_facebook": flattened_result.get("me.social.facebook", ""),
            "social_twitter": flattened_result.get("me.social.twitter", ""),
            "social_spotify": flattened_result.get("me.social.spotify", ""),
            "social_instagram": flattened_result.get("me.social.instagram", ""),
            "social_linkedin": flattened_result.get("me.social.linkedin", ""),
            "social_pinterest": flattened_result.get("me.social.pinterest", ""),
            "social_tiktok": flattened_result.get("me.social.tiktok", ""),
            "whitelist": flattened_result.get("me.whitelist", ""),
        }
        save_to_db(db, phone, cal_name, db_data)

        flattened_result["from_cache"] = False
        return jsonify(flattened_result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/sync", methods=["POST"])
def sync_api():
    """
    SYNC API wrapper - checks cache, calls external API if needed, stores in DB.

    Input: {
        "phone": "972...",
        "use_cache": true,      # optional, default true
        "refresh_days": 7,      # optional - refresh if older than N days
        "noapi": false          # optional - if true, only use cache
    }
    Output: { "phone_number": "...", "sync.first_name": "...", "sync.last_name": "...", "from_cache": bool }
    """
    if not SYNC_API_URL or not SYNC_API_TOKEN:
        return jsonify({"error": "SYNC API not configured"}), 501

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    phone = data.get("phone")
    use_cache = data.get("use_cache", True)
    refresh_days = data.get("refresh_days")
    noapi = data.get("noapi", False)

    if not phone:
        return jsonify({"error": "phone is required"}), 400

    try:
        db = get_db()
        from_cache = False

        # Check cache first
        if use_cache:
            db_result = get_from_sync_db(db, phone)
            if db_result:
                needs_refresh = False
                if refresh_days is not None:
                    if refresh_days == 0:
                        needs_refresh = True
                    else:
                        api_call_time_str = db_result.get("api_call_time", "")
                        if api_call_time_str:
                            api_call_time = datetime.fromisoformat(api_call_time_str)
                            if api_call_time.tzinfo is None:
                                api_call_time = api_call_time.replace(tzinfo=timezone.utc)
                            age_days = (datetime.now(timezone.utc) - api_call_time).days
                            needs_refresh = age_days >= refresh_days

                if not needs_refresh:
                    return jsonify({
                        "phone_number": phone,
                        "sync.first_name": db_result.get("first_name", ""),
                        "sync.last_name": db_result.get("last_name", ""),
                        "sync.api_call_time": db_result.get("api_call_time", ""),
                        "from_cache": True
                    })

        # If noapi mode, return cached data or empty
        if noapi:
            if use_cache and db_result:
                return jsonify({
                    "phone_number": phone,
                    "sync.first_name": db_result.get("first_name", ""),
                    "sync.last_name": db_result.get("last_name", ""),
                    "sync.api_call_time": db_result.get("api_call_time", ""),
                    "from_cache": True
                })
            else:
                return jsonify({
                    "phone_number": phone,
                    "sync.first_name": "NOT IN CACHE",
                    "sync.last_name": "",
                    "sync.api_call_time": "",
                    "from_cache": False
                })

        # Call the SYNC API
        api_result = sync_call_api(phone, SYNC_API_URL, SYNC_API_TOKEN)

        if api_result is None:
            flattened_result = sync_flatten_user_data({}, prefix="sync")
        else:
            flattened_result = sync_flatten_user_data(api_result, prefix="sync")

        flattened_result["phone_number"] = phone
        flattened_result["sync.api_call_time"] = datetime.now(timezone.utc).isoformat()

        # Save to cache
        save_to_sync_db(db, phone, "", {
            "name": flattened_result.get("sync.name", ""),
            "first_name": flattened_result.get("sync.first_name", ""),
            "last_name": flattened_result.get("sync.last_name", ""),
            "is_potential_spam": flattened_result.get("sync.is_potential_spam", ""),
            "is_business": flattened_result.get("sync.is_business", ""),
            "job_hint": flattened_result.get("sync.job_hint", ""),
            "company_hint": flattened_result.get("sync.company_hint", ""),
            "website_domain": flattened_result.get("sync.website_domain", ""),
            "company_domain": flattened_result.get("sync.company_domain", "")
        })

        flattened_result["from_cache"] = False
        return jsonify(flattened_result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/translate", methods=["POST"])
def translate():
    """
    Transliterate names to Hebrew (auto-detects language).

    Input: { "first": "David", "last": "Cohen" }
    Output: { "first": "דויד", "last": "כהן" }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    first = data.get("first", "")
    last = data.get("last", "")

    return jsonify({
        "first": transliterate_name(first),
        "last": transliterate_name(last)
    })


@app.route("/nicknames", methods=["GET"])
def nicknames():
    """
    Get all nickname variants for a given name.

    Input: ?name=David
    Output: { "names": ["David", "Dave", "Davey", "דוד"] }
    """
    name = request.args.get("name", "")
    if not name:
        return jsonify({"error": "name parameter is required"}), 400

    variants = get_all_nicknames_for_name(get_db(), name)
    return jsonify({"names": variants})


@app.route("/compare", methods=["POST"])
def compare():
    """
    Calculate similarity score between name sets.

    Input: { "first": "דוד", "last": "כהן", "names": ["David", "Dave"], "target_last": "Cohen" }
    Output: { "score": 85, "risk_tier": "HIGH", "breakdown": {...}, "explanation": "..." }

    The comparison uses ScoreEngine for explainable scoring.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    first = data.get("first", "")
    last = data.get("last", "")
    names = data.get("names", [])
    target_last = data.get("target_last", "")

    # Build cal_name from caller names + last name
    cal_name = ' '.join(names) + ' ' + target_last if target_last else ' '.join(names)

    engine = ScoreEngine(conn=get_db())
    result = engine.score_match(
        cal_name=cal_name.strip(),
        api_first=first,
        api_last=last,
    )

    return jsonify({
        "score": result["final_score"],
        "risk_tier": result["risk_tier"],
        "breakdown": result["breakdown"],
        "explanation": result["explanation"],
    })


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


# ============== Web Interface ==============

@app.route("/web/apis", methods=["GET"])
def web_apis():
    """Return list of available APIs."""
    apis = [
        {
            "name": "ME",
            "available": bool(API_URL and SID and TOKEN)
        },
        {
            "name": "SYNC",
            "available": bool(SYNC_API_URL and SYNC_API_TOKEN)
        }
    ]
    return jsonify({"apis": apis})


@app.route("/web/login")
def web_login_page():
    """Serve login page."""
    if count_users(get_db()) == 0:
        return redirect(url_for("web_user_bootstrap_page"))
    if get_logged_in_user():
        return redirect(url_for("web_index"))
    return render_template("login.html")


@app.route("/web/login", methods=["POST"])
@limiter.limit("5 per minute")  # Max 5 login attempts per minute per IP
def web_login():
    """Authenticate user and create session."""
    data = request.get_json() or {}
    username_input = data.get("username", "")
    password = data.get("password", "")

    if not username_input or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    username = normalize_username(username_input)
    db = get_db()
    user = get_user_by_username(db, username)

    if not user:
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    if int(user.get("active_flag", 1)) != 1:
        return jsonify({"success": False, "error": "User is inactive"}), 403

    # Check if account is locked due to failed login attempts
    failed_logins = int(user.get("failed_login_counter", 0))
    if failed_logins >= 5:
        return jsonify({"success": False, "error": "Account locked due to too many failed login attempts. Contact an administrator."}), 403

    if not verify_password_with_seed(password, user.get("seed", ""), user.get("hashed_password", "")):
        increment_failed_login(db, username)
        remaining = 5 - (failed_logins + 1)
        if remaining <= 0:
            return jsonify({"success": False, "error": "Account locked due to too many failed login attempts. Contact an administrator."}), 403
        return jsonify({"success": False, "error": f"Invalid credentials. {remaining} attempt(s) remaining before account lock."}), 401

    reset_failed_login_counter(db, username)
    update_last_login_datetime(db, username, datetime.now(timezone.utc).isoformat())

    session["username"] = username
    return jsonify({"success": True, "redirect": "/"})


@app.route("/web/logout", methods=["POST", "GET"])
def web_logout():
    """Clear user session."""
    session.clear()
    return redirect(url_for("web_login_page"))


@app.route("/web/users/bootstrap")
def web_user_bootstrap_page():
    """First-run user bootstrap page."""
    if count_users(get_db()) > 0:
        if get_logged_in_user():
            return redirect(url_for("web_index"))
        return redirect(url_for("web_login_page"))
    return render_template("user_bootstrap.html")


@app.route("/web/users/bootstrap", methods=["POST"])
def web_user_bootstrap_create():
    """Create first admin user and start session."""
    db = get_db()
    if count_users(db) > 0:
        return jsonify({"success": False, "error": "Bootstrap already completed"}), 409

    data = request.get_json() or {}
    username_input = data.get("username", "")
    password = data.get("password", "")
    email = (data.get("email", "") or "").strip()

    if not is_valid_username(username_input):
        return jsonify({"success": False, "error": "Invalid username format"}), 400

    if not is_valid_password(password):
        return jsonify({
            "success": False,
            "error": "Password must be at least 8 chars and include at least 3 of 4: lowercase, uppercase, digits, special chars",
        }), 400

    username = normalize_username(username_input)
    seed = secrets.token_hex(16)
    hashed_password = hash_password_with_seed(password, seed)

    create_user(
        db,
        username=username,
        seed=seed,
        hashed_password=hashed_password,
        email=email,
        admin_flag=1,
        active_flag=1,
    )
    update_last_login_datetime(db, username, datetime.now(timezone.utc).isoformat())

    session["username"] = username
    return jsonify({"success": True, "redirect": "/web/users"})


@app.route("/web/users")
@require_admin
def web_users_page():
    """Serve user management page."""
    current_user = get_logged_in_user()
    return render_template("users.html", current_username=current_user.get("username", ""))


@app.route("/web/users/list")
@require_admin
def web_users_list():
    """Return users for management screen."""
    users = list_users(get_db())
    normalized = []
    for user in users:
        normalized.append({
            "username": user.get("username", ""),
            "failed_login_counter": int(user.get("failed_login_counter", 0) or 0),
            "last_login_datetime": user.get("last_login_datetime", ""),
            "email": user.get("email", ""),
            "admin_flag": int(user.get("admin_flag", 0) or 0),
            "active_flag": int(user.get("active_flag", 1) or 1),
        })
    return jsonify({"users": normalized})


@app.route("/web/users/create", methods=["POST"])
@require_admin
def web_users_create():
    """Create additional user."""
    data = request.get_json() or {}
    username_input = data.get("username", "")
    password = data.get("password", "")
    email = (data.get("email", "") or "").strip()
    admin_flag = 1 if bool(data.get("admin_flag", False)) else 0
    active_flag = 1 if bool(data.get("active_flag", True)) else 0

    if not is_valid_username(username_input):
        return jsonify({"success": False, "error": "Invalid username format"}), 400

    if not is_valid_password(password):
        return jsonify({
            "success": False,
            "error": "Password must be at least 8 chars and include at least 3 of 4: lowercase, uppercase, digits, special chars",
        }), 400

    db = get_db()
    username = normalize_username(username_input)

    if get_user_by_username(db, username):
        return jsonify({"success": False, "error": "Username already exists"}), 409

    seed = secrets.token_hex(16)
    hashed_password = hash_password_with_seed(password, seed)
    create_user(
        db,
        username=username,
        seed=seed,
        hashed_password=hashed_password,
        email=email,
        admin_flag=admin_flag,
        active_flag=active_flag,
    )
    return jsonify({"success": True})


@app.route("/web/users/update", methods=["POST"])
@require_admin
def web_users_update():
    """Update user admin/active flags."""
    data = request.get_json() or {}
    username = normalize_username(data.get("username", ""))

    if not username:
        return jsonify({"success": False, "error": "username is required"}), 400

    db = get_db()
    user = get_user_by_username(db, username)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    admin_flag = data.get("admin_flag")
    active_flag = data.get("active_flag")

    admin_flag = None if admin_flag is None else (1 if bool(admin_flag) else 0)
    active_flag = None if active_flag is None else (1 if bool(active_flag) else 0)

    # Prevent disabling the last active admin account
    if active_flag == 0 and int(user.get("admin_flag", 0)) == 1:
        users = list_users(db)
        active_admins = [u for u in users if int(u.get("admin_flag", 0)) == 1 and int(u.get("active_flag", 0)) == 1]
        if len(active_admins) <= 1:
            return jsonify({"success": False, "error": "Cannot deactivate the last active admin"}), 400

    update_user_flags(db, username, admin_flag=admin_flag, active_flag=active_flag)
    return jsonify({"success": True})


@app.route("/web/users/reset-password", methods=["POST"])
@require_admin
@limiter.limit("10 per minute")  # Max 10 password resets per minute
def web_users_reset_password():
    """Reset user password (admin only)."""
    data = request.get_json() or {}
    username = normalize_username(data.get("username", ""))
    new_password = data.get("password", "")

    if not username:
        return jsonify({"success": False, "error": "username is required"}), 400

    if not new_password:
        return jsonify({"success": False, "error": "password is required"}), 400

    # Validate password strength
    if not is_valid_password(new_password):
        return jsonify({"success": False, "error": "Password must be at least 8 chars and include at least 3 of 4: lowercase, uppercase, digits, special chars"}), 400

    db = get_db()
    user = get_user_by_username(db, username)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    # Generate new seed and hash password
    seed = secrets.token_hex(16)
    hashed_password = hash_password_with_seed(new_password, seed)

    # Update password, reset failed login counter, and ensure user is active
    cursor = db.cursor()
    cursor.execute(
        """UPDATE users
           SET seed = ?, hashed_password = ?, failed_login_counter = 0, active_flag = 1
           WHERE username = ?""",
        (seed, hashed_password, username)
    )
    db.commit()

    return jsonify({"success": True, "message": f"Password reset for user '{username}'. Account unlocked and login attempts cleared."})

@app.route("/")
@app.route("/web")
def web_index():
    """Serve the web interface."""
    current_user = get_logged_in_user()
    is_admin = int(current_user.get("admin_flag", 0)) == 1 if current_user else False
    return render_template("index.html", is_admin=is_admin)


@app.route("/web/query")
def web_query_page():
    """Serve the single query interface."""
    current_user = get_logged_in_user()
    is_admin = int(current_user.get("admin_flag", 0)) == 1 if current_user else False
    return render_template("query.html", is_admin=is_admin)


@app.route("/web/query", methods=["POST"])
def web_query():
    """
    Process single phone query.

    Input: { "phone": "...", "first_name": "...", "last_name": "...", "refresh_days": 0, "apis": "me" }
    Output: { "success": true, "result": {...}, "from_cache": bool }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON body required"})

    phone = data.get("phone", "").strip()
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    refresh_days = data.get("refresh_days", 7)  # Default 7 days
    me_cache_only = data.get("me_cache_only", False)
    sync_cache_only = data.get("sync_cache_only", False)
    apis_str = data.get("apis", "me")
    selected_apis = [a.strip().lower() for a in apis_str.split(',') if a.strip()]
    use_me = 'me' in selected_apis
    use_sync = 'sync' in selected_apis

    if not phone:
        return jsonify({"success": False, "error": "מספר טלפון נדרש"})

    # Convert phone to international format
    phone_list = convert_to_international([phone])
    phone = phone_list[0]

    # Validate phone
    if not validate_phone_numbers([phone]):
        return jsonify({"success": False, "error": "מספר טלפון לא תקין"})

    cal_name = f"{first_name} {last_name}".strip()

    # Validate cal_name is provided
    if not cal_name:
        return jsonify({"success": False, "error": "שם איש קשר נדרש"})

    # Validate cal_name is Hebrew
    if not is_hebrew(cal_name):
        return jsonify({"success": False, "error": "שם איש קשר חייב להיות בעברית"})

    try:
        db = get_db()
        from_cache = False
        result = {
            "phone_number": phone,
            "cal_name": cal_name,
        }

        # Check ME cache first (only if ME is selected)
        if use_me:
            db_result = get_from_db_with_age(db, phone)

            if db_result:
                # Determine if we should use cache or refresh
                # me_cache_only=True → always use cache
                # refresh_days=0 → always refresh (call API)
                # refresh_days>0 → refresh if older than N days
                use_cached = False
                if me_cache_only:
                    use_cached = True
                elif refresh_days == 0:
                    use_cached = False  # Always call API
                else:
                    # Check age
                    api_call_time_str = db_result.get("api_call_time", "")
                    if api_call_time_str:
                        api_call_time = datetime.fromisoformat(api_call_time_str)
                        if api_call_time.tzinfo is None:
                            api_call_time = api_call_time.replace(tzinfo=timezone.utc)
                        age_days = (datetime.now(timezone.utc) - api_call_time).days
                        use_cached = age_days < refresh_days
                    else:
                        use_cached = False  # No timestamp, needs refresh

                if use_cached:
                    # Update cal_name if different
                    if db_result.get("cal_name") != cal_name and cal_name:
                        db_result["cal_name"] = cal_name
                        save_to_db(db, phone, cal_name, db_result, update_time=False)

                    result = convert_db_to_response(db_result)
                    # Restore input values (don't use cached phone_number/cal_name)
                    result["phone_number"] = phone
                    result["cal_name"] = cal_name or db_result.get("cal_name", "")
                    from_cache = True
                else:
                    db_result = None  # Force refresh

        # If cache-only mode and ME selected but not in cache, return not found
        if use_me and me_cache_only and not from_cache:
            result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
            result["phone_number"] = phone
            result["cal_name"] = cal_name
            result["me.common_name"] = "NOT IN CACHE"

        # Call ME API if needed and selected (not cache-only mode)
        if use_me and not from_cache and not me_cache_only:
            api_result = me_call_api(phone, API_URL, SID, TOKEN)

            if api_result is None:
                flattened_result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
            else:
                flattened_result = clean_data_for_db(me_flatten_user_data(api_result, prefix="me"))

            flattened_result["phone_number"] = phone
            flattened_result["cal_name"] = cal_name
            flattened_result["me.api_call_time"] = datetime.now(timezone.utc).isoformat()

            # Save to DB
            db_data = {
                "common_name": flattened_result.get("me.common_name", ""),
                "me_profile_name": flattened_result.get("me.profile_name", ""),
                "result_strength": flattened_result.get("me.result_strength", ""),
                "user_first_name": flattened_result.get("me.first_name", ""),
                "user_last_name": flattened_result.get("me.last_name", ""),
                "user_email": flattened_result.get("me.email", ""),
                "user_email_confirmed": flattened_result.get("me.email_confirmed", ""),
                "user_profile_picture": flattened_result.get("me.profile_picture", ""),
                "user_gender": flattened_result.get("me.gender", ""),
                "user_is_verified": flattened_result.get("me.is_verified", ""),
                "user_slogan": flattened_result.get("me.slogan", ""),
                "social_facebook": flattened_result.get("me.social.facebook", ""),
                "social_twitter": flattened_result.get("me.social.twitter", ""),
                "social_spotify": flattened_result.get("me.social.spotify", ""),
                "social_instagram": flattened_result.get("me.social.instagram", ""),
                "social_linkedin": flattened_result.get("me.social.linkedin", ""),
                "social_pinterest": flattened_result.get("me.social.pinterest", ""),
                "social_tiktok": flattened_result.get("me.social.tiktok", ""),
                "whitelist": flattened_result.get("me.whitelist", ""),
            }
            save_to_db(db, phone, cal_name, db_data)
            result = flattened_result

        # Calculate ME translation and matching (only if ME is selected)
        if use_me:
            # Clean API results: remove apostrophes
            me_common_name = str(result.get("me.common_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
            me_first_name = str(result.get("me.first_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
            me_last_name = str(result.get("me.last_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
            # Update result with cleaned values
            result["me.common_name"] = me_common_name
            result["me.first_name"] = me_first_name
            result["me.last_name"] = me_last_name

            # Translate each field only if it's NOT Hebrew
            translated_common = transliterate_name(me_common_name) if me_common_name and not is_hebrew(me_common_name) else ""
            translated_first = transliterate_name(me_first_name) if me_first_name and not is_hebrew(me_first_name) else ""
            translated_last = transliterate_name(me_last_name) if me_last_name and not is_hebrew(me_last_name) else ""

            # Combine translated fields (only non-empty ones)
            all_translated = f"{translated_common} {translated_first} {translated_last}".split()
            result["me.translated"] = ' '.join(dict.fromkeys(w for w in all_translated if w))

            # Calculate matching score
            if cal_name:
                engine = ScoreEngine(conn=db)
                score_result = engine.score_match(
                    cal_name=cal_name,
                    api_first=me_first_name,
                    api_last=me_last_name,
                    api_common_name=me_common_name,
                    api_source="ME"
                )
                result["me.matching"] = score_result["final_score"]
                result["me.risk_tier"] = score_result["risk_tier"]
                result["me.score_explanation"] = score_result["explanation"]
            else:
                result["me.matching"] = 0

        # Call SYNC API if selected
        if use_sync and SYNC_API_URL and SYNC_API_TOKEN:
            try:
                sync_from_cache = False
                sync_db_result = get_from_sync_db(db, phone)

                # Check if we have cached SYNC data and if refresh is needed
                if sync_db_result:
                    # sync_cache_only=True → always use cache
                    # refresh_days=0 → always refresh (call API)
                    # refresh_days>0 → refresh if older than N days
                    if sync_cache_only:
                        sync_from_cache = True
                    elif refresh_days == 0:
                        sync_from_cache = False  # Always call API
                    else:
                        # Check age
                        sync_time_str = sync_db_result.get("api_call_time", "")
                        if sync_time_str:
                            sync_time = datetime.fromisoformat(sync_time_str)
                            if sync_time.tzinfo is None:
                                sync_time = sync_time.replace(tzinfo=timezone.utc)
                            sync_age_days = (datetime.now(timezone.utc) - sync_time).days
                            sync_from_cache = sync_age_days < refresh_days
                        else:
                            sync_from_cache = False  # No timestamp, needs refresh

                if sync_from_cache and sync_db_result:
                    result["sync.first_name"] = sync_db_result.get("first_name", "")
                    result["sync.last_name"] = sync_db_result.get("last_name", "")
                    result["sync.api_call_time"] = sync_db_result.get("api_call_time", "")
                elif sync_cache_only:
                    # Cache only mode - check if we have cached data
                    if sync_db_result:
                        result["sync.first_name"] = sync_db_result.get("first_name", "")
                        result["sync.last_name"] = sync_db_result.get("last_name", "")
                        result["sync.api_call_time"] = sync_db_result.get("api_call_time", "")
                    else:
                        result["sync.first_name"] = "NOT IN CACHE"
                        result["sync.last_name"] = ""
                else:
                    # Call SYNC API
                    sync_api_result = sync_call_api(phone, SYNC_API_URL, SYNC_API_TOKEN)
                    if sync_api_result:
                        sync_flat = sync_flatten_user_data(sync_api_result, prefix="sync")
                    else:
                        sync_flat = sync_flatten_user_data({}, prefix="sync")
                    result["sync.first_name"] = sync_flat.get("sync.first_name", "")
                    result["sync.last_name"] = sync_flat.get("sync.last_name", "")
                    result["sync.api_call_time"] = datetime.now(timezone.utc).isoformat()

                    # Save to cache
                    save_to_sync_db(db, phone, cal_name, {
                        "name": sync_flat.get("sync.name", ""),
                        "first_name": sync_flat.get("sync.first_name", ""),
                        "last_name": sync_flat.get("sync.last_name", ""),
                        "is_potential_spam": sync_flat.get("sync.is_potential_spam", ""),
                        "is_business": sync_flat.get("sync.is_business", ""),
                        "job_hint": sync_flat.get("sync.job_hint", ""),
                        "company_hint": sync_flat.get("sync.company_hint", ""),
                        "website_domain": sync_flat.get("sync.website_domain", ""),
                        "company_domain": sync_flat.get("sync.company_domain", "")
                    })
                # Calculate SYNC translation and matching score
                # Clean API results: remove apostrophes
                sync_first = str(result.get("sync.first_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
                sync_last = str(result.get("sync.last_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
                # Update result with cleaned values
                result["sync.first_name"] = sync_first
                result["sync.last_name"] = sync_last

                # Translate each field only if it's NOT Hebrew
                sync_translated_first = transliterate_name(sync_first) if sync_first and not is_hebrew(sync_first) else ""
                sync_translated_last = transliterate_name(sync_last) if sync_last and not is_hebrew(sync_last) else ""

                # Combine translated fields (only non-empty ones)
                all_sync_translated = f"{sync_translated_first} {sync_translated_last}".split()
                result["sync.translated"] = ' '.join(dict.fromkeys(w for w in all_sync_translated if w))

                if cal_name and (sync_first or sync_last):
                    engine = ScoreEngine(conn=db)
                    sync_score_result = engine.score_match(
                        cal_name=cal_name,
                        api_first=sync_first,
                        api_last=sync_last,
                        api_source="SYNC"
                    )
                    result["sync.matching"] = sync_score_result["final_score"]
                    result["sync.risk_tier"] = sync_score_result["risk_tier"]
                    result["sync.score_explanation"] = sync_score_result["explanation"]
                else:
                    result["sync.matching"] = 0

            except Exception as sync_error:
                result["sync.first_name"] = f"ERROR: {sync_error}"
                result["sync.last_name"] = ""
                result["sync.matching"] = 0

        return jsonify({
            "success": True,
            "result": result,
            "from_cache": from_cache
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/web/process", methods=["POST"])
def web_process():
    """
    Process uploaded file via web interface.

    Input: multipart form with 'file', 'refresh_days', 'apis', 'me_cache_only', 'sync_cache_only'
    Output: { "success": true, "file_id": "...", "total": N, "from_cache": N, "api_calls": N }
    """
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    # Validate file extension
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Invalid file type. Only .xlsx and .csv files are allowed"}), 400

    # Secure the filename
    filename = secure_filename(file.filename)

    # Get refresh_days (default 7)
    try:
        refresh_days = int(request.form.get('refresh_days', 7))
    except ValueError:
        refresh_days = 7

    # Get cache-only flags
    me_cache_only = request.form.get('me_cache_only', '').lower() == 'true'
    sync_cache_only = request.form.get('sync_cache_only', '').lower() == 'true'

    # Get selected APIs
    apis_str = request.form.get('apis', 'me')
    selected_apis = [a.strip().lower() for a in apis_str.split(',') if a.strip()]
    if not selected_apis:
        selected_apis = ['me']

    use_me = 'me' in selected_apis
    use_sync = 'sync' in selected_apis and SYNC_API_URL and SYNC_API_TOKEN

    # Generate file suffix based on selected APIs
    if use_me and use_sync:
        file_suffix = "_me_sync"
    elif use_sync:
        file_suffix = "_sync"
    else:
        file_suffix = "_me"

    try:
        # SECURITY: Validate file size first
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Seek back to start
        validate_file_size(file_size)

        # Read the file
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            data = pd.read_csv(file, dtype=str, header=None)
        elif filename.endswith('.xlsx'):
            data = pd.read_excel(file, dtype=str, header=None)
        else:
            return jsonify({"success": False, "error": "פורמט קובץ לא נתמך. השתמש ב-.xlsx או .csv"})

        # SECURITY: Validate row count
        if len(data) > 100000:  # MAX_ROWS
            return jsonify({"success": False, "error": f"File too large: {len(data)} rows (max 100,000)"}), 400

        if data.shape[1] != 3:
            return jsonify({"success": False, "error": f"הקובץ חייב להכיל בדיוק 3 עמודות (טלפון, שם פרטי, שם משפחה). נמצאו {data.shape[1]} עמודות"})

        if len(data) == 0:
            return jsonify({"success": False, "error": "הקובץ ריק"})

        # Detect and remove header row
        # Check if first row looks like headers (common header words or non-Hebrew text)
        first_row = data.iloc[0]
        header_indicators = ['phone', 'טלפון', 'מספר', 'first', 'last', 'שם', 'name', 'פרטי', 'משפחה']
        is_header = False
        for cell in first_row:
            cell_str = str(cell).lower().strip() if pd.notna(cell) else ""
            if any(indicator in cell_str for indicator in header_indicators):
                is_header = True
                break
            # Also check if first cell doesn't look like a phone number
            if cell_str and not cell_str.replace('+', '').replace('-', '').replace(' ', '').isdigit():
                is_header = True
                break

        start_row = 1 if is_header else 0
        data = data.iloc[start_row:].reset_index(drop=True)

        if len(data) == 0:
            return jsonify({"success": False, "error": "הקובץ ריק (רק שורת כותרת)"})

        # Validate all rows and collect errors
        errors = []
        valid_rows = []

        def clean_name(name):
            """Clean name: remove apostrophes and extra whitespace."""
            if not name:
                return ""
            return name.replace("'", "").replace("'", "").replace("`", "").strip()

        def is_valid_phone(phone):
            """Check if phone is valid local or international format."""
            if not phone:
                return False
            phone = str(phone).strip().replace('-', '').replace(' ', '').replace('+', '')
            # Israeli local: 05x, 07x (9-10 digits)
            if phone.startswith('05') or phone.startswith('07'):
                return len(phone) >= 9 and len(phone) <= 10 and phone.isdigit()
            # International: 972... (11-12 digits)
            if phone.startswith('972'):
                return len(phone) >= 11 and len(phone) <= 12 and phone.isdigit()
            return False

        for idx, row in data.iterrows():
            excel_row = idx + 2 if is_header else idx + 1  # Excel row number (1-indexed, accounting for header)
            row_errors = []

            phone = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
            first_name = clean_name(str(row.iloc[1])) if pd.notna(row.iloc[1]) else ""
            last_name = clean_name(str(row.iloc[2])) if pd.notna(row.iloc[2]) else ""

            # Validate phone
            if not phone:
                row_errors.append(f"שורה {excel_row}, עמודה A: טלפון ריק")
            elif not is_valid_phone(phone):
                row_errors.append(f"שורה {excel_row}, עמודה A: טלפון לא תקין '{phone}'")

            # Validate first name
            if not first_name:
                row_errors.append(f"שורה {excel_row}, עמודה B: שם פרטי ריק")
            elif not is_hebrew(first_name):
                row_errors.append(f"שורה {excel_row}, עמודה B: שם פרטי חייב להיות בעברית '{first_name}'")

            # Validate last name
            if not last_name:
                row_errors.append(f"שורה {excel_row}, עמודה C: שם משפחה ריק")
            elif not is_hebrew(last_name):
                row_errors.append(f"שורה {excel_row}, עמודה C: שם משפחה חייב להיות בעברית '{last_name}'")

            if row_errors:
                errors.extend(row_errors)
            else:
                valid_rows.append({
                    "phone": phone,
                    "first_name": first_name,
                    "last_name": last_name,
                    "cal_name": f"{first_name} {last_name}"
                })

        # If there are errors, return them
        if errors:
            error_list = "\n".join(errors[:20])  # Limit to first 20 errors
            if len(errors) > 20:
                error_list += f"\n... ועוד {len(errors) - 20} שגיאות"
            return jsonify({"success": False, "error": f"שגיאות בקובץ:\n{error_list}"})

        if not valid_rows:
            return jsonify({"success": False, "error": "לא נמצאו שורות תקינות בקובץ"})

        # Convert phones to international format
        for row in valid_rows:
            converted = convert_to_international([row["phone"]])
            row["phone"] = converted[0]

        results = []
        me_from_cache_count = 0
        me_api_calls_count = 0
        sync_from_cache_count = 0
        sync_api_calls_count = 0

        db = get_db()

        # Process each validated row
        for row_data in valid_rows:
            phone = row_data["phone"]
            cal_name = row_data["cal_name"]

            result = {
                "phone_number": phone,
                "cal_name": cal_name,
            }

            try:
                # === ME API Processing ===
                if use_me:
                    me_from_cache = False
                    db_result = get_from_db_with_age(db, phone)

                    if db_result:
                        # Determine if we should use cache or refresh
                        # me_cache_only=True → always use cache
                        # refresh_days=0 → always refresh (call API)
                        # refresh_days>0 → refresh if older than N days
                        use_cached = False
                        if me_cache_only:
                            use_cached = True
                        elif refresh_days == 0:
                            use_cached = False  # Always call API
                        else:
                            # Check age
                            api_call_time_str = db_result.get("api_call_time", "")
                            if api_call_time_str:
                                api_call_time = datetime.fromisoformat(api_call_time_str)
                                if api_call_time.tzinfo is None:
                                    api_call_time = api_call_time.replace(tzinfo=timezone.utc)
                                age_days = (datetime.now(timezone.utc) - api_call_time).days
                                use_cached = age_days < refresh_days
                            else:
                                use_cached = False  # No timestamp, needs refresh

                        if use_cached:
                            # Update cal_name if different
                            if db_result.get("cal_name") != cal_name and cal_name:
                                db_result["cal_name"] = cal_name
                                save_to_db(db, phone, cal_name, db_result, update_time=False)

                            me_data = convert_db_to_response(db_result)
                            for key, value in me_data.items():
                                result[key] = value
                            # Restore input values (don't use cached phone_number/cal_name)
                            result["phone_number"] = phone
                            result["cal_name"] = cal_name
                            me_from_cache = True
                            me_from_cache_count += 1
                        else:
                            db_result = None  # Force refresh

                    # If cache-only mode and ME not in cache
                    if me_cache_only and not me_from_cache:
                        me_empty = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
                        for key, value in me_empty.items():
                            result[key] = value
                        result["me.common_name"] = "NOT IN CACHE"

                    # Call ME API if needed (not cache-only mode)
                    elif not me_from_cache and not me_cache_only:
                        api_result = me_call_api(phone, API_URL, SID, TOKEN)
                        me_api_calls_count += 1

                        if api_result is None:
                            flattened_result = clean_data_for_db(me_flatten_user_data({}, prefix="me"))
                        else:
                            flattened_result = clean_data_for_db(me_flatten_user_data(api_result, prefix="me"))

                        flattened_result["me.api_call_time"] = datetime.now(timezone.utc).isoformat()

                        # Save to DB
                        db_data = {
                            "common_name": flattened_result.get("me.common_name", ""),
                            "me_profile_name": flattened_result.get("me.profile_name", ""),
                            "result_strength": flattened_result.get("me.result_strength", ""),
                            "user_first_name": flattened_result.get("me.first_name", ""),
                            "user_last_name": flattened_result.get("me.last_name", ""),
                            "user_email": flattened_result.get("me.email", ""),
                            "user_email_confirmed": flattened_result.get("me.email_confirmed", ""),
                            "user_profile_picture": flattened_result.get("me.profile_picture", ""),
                            "user_gender": flattened_result.get("me.gender", ""),
                            "user_is_verified": flattened_result.get("me.is_verified", ""),
                            "user_slogan": flattened_result.get("me.slogan", ""),
                            "social_facebook": flattened_result.get("me.social.facebook", ""),
                            "social_twitter": flattened_result.get("me.social.twitter", ""),
                            "social_spotify": flattened_result.get("me.social.spotify", ""),
                            "social_instagram": flattened_result.get("me.social.instagram", ""),
                            "social_linkedin": flattened_result.get("me.social.linkedin", ""),
                            "social_pinterest": flattened_result.get("me.social.pinterest", ""),
                            "social_tiktok": flattened_result.get("me.social.tiktok", ""),
                            "whitelist": flattened_result.get("me.whitelist", ""),
                        }
                        save_to_db(db, phone, cal_name, db_data)

                        for key, value in flattened_result.items():
                            result[key] = value

                # === SYNC API Processing ===
                if use_sync:
                    sync_from_cache = False
                    sync_db_result = get_from_sync_db(db, phone)

                    if sync_db_result:
                        # Determine if we should use cache or refresh
                        use_cached = False
                        if sync_cache_only:
                            use_cached = True
                        elif refresh_days == 0:
                            use_cached = False  # Always call API
                        else:
                            # Check age
                            sync_time_str = sync_db_result.get("api_call_time", "")
                            if sync_time_str:
                                sync_time = datetime.fromisoformat(sync_time_str)
                                if sync_time.tzinfo is None:
                                    sync_time = sync_time.replace(tzinfo=timezone.utc)
                                sync_age_days = (datetime.now(timezone.utc) - sync_time).days
                                use_cached = sync_age_days < refresh_days
                            else:
                                use_cached = False

                        if use_cached:
                            result["sync.first_name"] = sync_db_result.get("first_name", "")
                            result["sync.last_name"] = sync_db_result.get("last_name", "")
                            result["sync.api_call_time"] = sync_db_result.get("api_call_time", "")
                            sync_from_cache = True
                            sync_from_cache_count += 1
                        else:
                            sync_db_result = None

                    # If cache-only mode and SYNC not in cache
                    if sync_cache_only and not sync_from_cache:
                        result["sync.first_name"] = "NOT IN CACHE"
                        result["sync.last_name"] = ""
                        result["sync.api_call_time"] = ""

                    # Call SYNC API if needed (not cache-only mode)
                    elif not sync_from_cache and not sync_cache_only:
                        sync_api_result = sync_call_api(phone, SYNC_API_URL, SYNC_API_TOKEN)
                        sync_api_calls_count += 1

                        if sync_api_result:
                            sync_flat = sync_flatten_user_data(sync_api_result, prefix="sync")
                        else:
                            sync_flat = sync_flatten_user_data({}, prefix="sync")

                        result["sync.first_name"] = sync_flat.get("sync.first_name", "")
                        result["sync.last_name"] = sync_flat.get("sync.last_name", "")
                        result["sync.api_call_time"] = datetime.now(timezone.utc).isoformat()

                        # Save to cache
                        save_to_sync_db(db, phone, cal_name, {
                            "name": sync_flat.get("sync.name", ""),
                            "first_name": sync_flat.get("sync.first_name", ""),
                            "last_name": sync_flat.get("sync.last_name", ""),
                            "is_potential_spam": sync_flat.get("sync.is_potential_spam", ""),
                            "is_business": sync_flat.get("sync.is_business", ""),
                            "job_hint": sync_flat.get("sync.job_hint", ""),
                            "company_hint": sync_flat.get("sync.company_hint", ""),
                            "website_domain": sync_flat.get("sync.website_domain", ""),
                            "company_domain": sync_flat.get("sync.company_domain", "")
                        })

                results.append(result)

            except Exception as e:
                result["me.common_name"] = f"ERROR: {e}" if use_me else ""
                result["sync.first_name"] = f"ERROR: {e}" if use_sync else ""
                results.append(result)

        # Post-process: calculate translations and matching scores
        for result in results:
            cal_name = str(result.get("cal_name", "") or "")

            # === ME Translation and Matching ===
            if use_me:
                # Clean API results: remove apostrophes
                me_common_name = str(result.get("me.common_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
                me_first_name = str(result.get("me.first_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
                me_last_name = str(result.get("me.last_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
                # Update result with cleaned values
                result["me.common_name"] = me_common_name
                result["me.first_name"] = me_first_name
                result["me.last_name"] = me_last_name

                # Skip translation/matching for error or not-in-cache results
                is_error_result = me_common_name.startswith("ERROR:") or me_common_name == "NOT IN CACHE"

                if is_error_result:
                    result["me.translated"] = ""
                    result["me.matching"] = 0
                else:
                    # Translate each field only if it's NOT Hebrew
                    translated_common = transliterate_name(me_common_name) if me_common_name and not is_hebrew(me_common_name) else ""
                    translated_first = transliterate_name(me_first_name) if me_first_name and not is_hebrew(me_first_name) else ""
                    translated_last = transliterate_name(me_last_name) if me_last_name and not is_hebrew(me_last_name) else ""

                    # Combine translated fields (only non-empty ones)
                    all_translated = f"{translated_common} {translated_first} {translated_last}".split()
                    result["me.translated"] = ' '.join(dict.fromkeys(w for w in all_translated if w))

                    # Calculate matching score
                    if cal_name:
                        engine = ScoreEngine(conn=db)
                        score_result = engine.score_match(
                            cal_name=cal_name,
                            api_first=me_first_name,
                            api_last=me_last_name,
                            api_common_name=me_common_name,
                            api_source="ME"
                        )
                        result["me.matching"] = score_result["final_score"]
                        result["me.risk_tier"] = score_result["risk_tier"]
                    else:
                        result["me.matching"] = 0

            # === SYNC Translation and Matching ===
            if use_sync:
                # Clean API results: remove apostrophes
                sync_first = str(result.get("sync.first_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
                sync_last = str(result.get("sync.last_name", "") or "").replace("'", "").replace("'", "").replace("`", "")
                # Update result with cleaned values
                result["sync.first_name"] = sync_first
                result["sync.last_name"] = sync_last

                # Skip translation/matching for error or not-in-cache results
                is_sync_error = sync_first.startswith("ERROR:") or sync_first == "NOT IN CACHE"

                if is_sync_error:
                    result["sync.translated"] = ""
                    result["sync.matching"] = 0
                else:
                    # Translate each field only if it's NOT Hebrew
                    sync_translated_first = transliterate_name(sync_first) if sync_first and not is_hebrew(sync_first) else ""
                    sync_translated_last = transliterate_name(sync_last) if sync_last and not is_hebrew(sync_last) else ""

                    # Combine translated fields (only non-empty ones)
                    all_sync_translated = f"{sync_translated_first} {sync_translated_last}".split()
                    result["sync.translated"] = ' '.join(dict.fromkeys(w for w in all_sync_translated if w))

                    # Calculate matching score
                    if cal_name and (sync_first or sync_last):
                        engine = ScoreEngine(conn=db)
                        sync_score_result = engine.score_match(
                            cal_name=cal_name,
                            api_first=sync_first,
                            api_last=sync_last,
                            api_source="SYNC"
                        )
                        result["sync.matching"] = sync_score_result["final_score"]
                        result["sync.risk_tier"] = sync_score_result["risk_tier"]
                    else:
                        result["sync.matching"] = 0

        # Create DataFrame
        result_df = pd.DataFrame(results).astype(str)

        # Define column order based on selected APIs
        desired_order = ["phone_number", "cal_name"]

        if use_me:
            desired_order.extend([
                "me.common_name", "me.matching", "me.risk_tier", "me.translated",
                "me.result_strength", "me.profile_name",
                "me.first_name", "me.last_name", "me.email", "me.email_confirmed",
                "me.profile_picture", "me.gender", "me.is_verified", "me.slogan",
                "me.social.facebook", "me.social.twitter", "me.social.spotify",
                "me.social.instagram", "me.social.linkedin", "me.social.pinterest",
                "me.social.tiktok", "me.whitelist", "me.api_call_time"
            ])

        if use_sync:
            desired_order.extend([
                "sync.first_name", "sync.last_name", "sync.matching", "sync.risk_tier", "sync.translated",
                "sync.api_call_time"
            ])

        existing_columns = [col for col in desired_order if col in result_df.columns]
        result_df = result_df.reindex(columns=existing_columns)

        # Save to temp file
        file_id = str(uuid.uuid4())
        temp_path = os.path.join(tempfile.gettempdir(), f"result_{file_id}.xlsx")
        result_df.to_excel(temp_path, index=False, engine="openpyxl")

        # Store file info
        PROCESSED_FILES[file_id] = {
            "path": temp_path,
            "created": datetime.now(),
            "original_name": os.path.splitext(file.filename)[0] + file_suffix + ".xlsx"
        }

        total_from_cache = me_from_cache_count + sync_from_cache_count
        total_api_calls = me_api_calls_count + sync_api_calls_count

        return jsonify({
            "success": True,
            "file_id": file_id,
            "total": len(results),
            "from_cache": total_from_cache,
            "api_calls": total_api_calls
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/web/download/<file_id>")
def web_download(file_id):
    """Download processed file - requires authentication."""
    # Require user to be logged in
    if 'user_id' not in session:
        return redirect(url_for('web_login_page'))

    if file_id not in PROCESSED_FILES:
        return jsonify({"error": "File not found"}), 404

    file_info = PROCESSED_FILES[file_id]
    if not os.path.exists(file_info["path"]):
        return jsonify({"error": "File expired"}), 404

    return send_file(
        file_info["path"],
        as_attachment=True,
        download_name=file_info["original_name"],
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ============== Nicknames Management ==============

@app.route("/web/nicknames")
def web_nicknames_page():
    """Serve the nicknames management page."""
    current_user = get_logged_in_user()
    is_admin = int(current_user.get("admin_flag", 0)) == 1 if current_user else False
    return render_template("nicknames.html", is_admin=is_admin)


@app.route("/web/nicknames/list")
def web_nicknames_list():
    """Return list of all nicknames."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT formal_name, all_names FROM nicknames ORDER BY formal_name")
    rows = cursor.fetchall()

    nicknames = []
    total_nicknames = 0
    for row in rows:
        formal_name, all_names = row
        nicknames.append({
            "formal_name": formal_name,
            "all_names": all_names
        })
        # Count individual nicknames
        if all_names:
            total_nicknames += len(all_names.split(','))

    return jsonify({
        "nicknames": nicknames,
        "total_names": len(nicknames),
        "total_nicknames": total_nicknames
    })


@app.route("/web/nicknames/upload", methods=["POST"])
def web_nicknames_upload():
    """Upload and import nicknames from file (JSON, Excel, or CSV)."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "לא הועלה קובץ"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "לא נבחר קובץ"})

    # Secure the filename
    filename = secure_filename(file.filename)
    filename_lower = filename.lower()

    # Validate file extension (allow JSON in addition to xlsx/csv)
    if not (filename_lower.endswith('.json') or allowed_file(filename)):
        return jsonify({"success": False, "error": "סוג קובץ לא חוקי. רק קבצי .json, .xlsx ו-.csv מותרים"}), 400

    mode = request.form.get('mode', 'add')  # 'add' or 'overwrite'

    try:
        # Validate file size first
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Seek back to start
        validate_file_size(file_size)

        # Read the file based on format
        if filename_lower.endswith('.json'):
            # Parse JSON file
            import json
            content = file.read().decode('utf-8')
            nicknames_list = json.loads(content)

            # SECURITY: Validate and sanitize the data
            nicknames_list = validate_nicknames_data(nicknames_list)

            # Convert to DataFrame for uniform processing
            df = pd.DataFrame(nicknames_list)

        elif filename_lower.endswith('.csv'):
            df = pd.read_csv(file, dtype=str)
        elif filename_lower.endswith('.xlsx'):
            df = pd.read_excel(file, dtype=str)
        else:
            return jsonify({"success": False, "error": "פורמט קובץ לא נתמך. השתמש ב-.json, .xlsx או .csv"})

        # Check columns
        if df.shape[1] < 2 or 'formal_name' not in df.columns or 'all_names' not in df.columns:
            return jsonify({"success": False, "error": "הקובץ חייב להכיל עמודות formal_name ו-all_names"})

        # Ensure we have the right columns (rename only if needed for CSV/Excel)
        if not filename_lower.endswith('.json'):
            df.columns = ['formal_name', 'all_names'] + list(df.columns[2:])

            # SECURITY: Validate and sanitize CSV/Excel data
            data_list = df.to_dict('records')
            data_list = validate_nicknames_data(data_list)
            df = pd.DataFrame(data_list)

        db = get_db()
        cursor = db.cursor()

        added = 0
        updated = 0
        skipped = 0

        for _, row in df.iterrows():
            formal_name = str(row['formal_name']).strip() if pd.notna(row['formal_name']) else ""
            all_names = str(row['all_names']).strip() if pd.notna(row['all_names']) else ""

            if not formal_name or not all_names:
                skipped += 1
                continue

            # Check if formal_name exists
            cursor.execute("SELECT all_names FROM nicknames WHERE formal_name = ?", (formal_name,))
            existing = cursor.fetchone()

            if existing:
                if mode == 'overwrite':
                    # Replace with new nicknames
                    cursor.execute(
                        "UPDATE nicknames SET all_names = ? WHERE formal_name = ?",
                        (all_names, formal_name)
                    )
                    updated += 1
                else:  # add mode
                    # Merge nicknames - add unique ones
                    existing_names = set(n.strip() for n in existing[0].split(',') if n.strip())
                    new_names = set(n.strip() for n in all_names.split(',') if n.strip())
                    merged = existing_names | new_names
                    merged_str = ','.join(sorted(merged))
                    cursor.execute(
                        "UPDATE nicknames SET all_names = ? WHERE formal_name = ?",
                        (merged_str, formal_name)
                    )
                    if new_names - existing_names:  # Only count if we actually added something
                        updated += 1
                    else:
                        skipped += 1
            else:
                # New formal name - insert
                cursor.execute(
                    "INSERT INTO nicknames (formal_name, all_names) VALUES (?, ?)",
                    (formal_name, all_names)
                )
                added += 1

        db.commit()

        return jsonify({
            "success": True,
            "added": added,
            "updated": updated,
            "skipped": skipped
        })

    except ValidationError as e:
        return jsonify({"success": False, "error": f"Validation error: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/web/nicknames/download")
def web_nicknames_download():
    """Download current nicknames as JSON file - requires authentication."""
    # Require user to be logged in
    if 'user_id' not in session:
        return redirect(url_for('web_login_page'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT formal_name, all_names FROM nicknames ORDER BY formal_name")
    rows = cursor.fetchall()

    # Convert to list of dicts
    nicknames_data = []
    for row in rows:
        nicknames_data.append({
            'formal_name': row[0],
            'all_names': row[1]
        })

    # Save to temp file
    temp_path = os.path.join(tempfile.gettempdir(), "nicknames_export.json")
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(nicknames_data, f, ensure_ascii=False, indent=2)

    return send_file(
        temp_path,
        as_attachment=True,
        download_name="nicknames.json",
        mimetype="application/json"
    )


@app.route("/web/nicknames/backup", methods=["POST"])
def web_nicknames_backup():
    """Backup nicknames to local nicknames.xlsx file."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT formal_name, all_names FROM nicknames ORDER BY formal_name")
        rows = cursor.fetchall()

        df = pd.DataFrame(rows, columns=['formal_name', 'all_names'])

        # Save to local nicknames.xlsx in the project directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        backup_path = os.path.join(script_dir, "nicknames.xlsx")
        df.to_excel(backup_path, index=False, engine="openpyxl")

        return jsonify({
            "success": True,
            "message": f"גיבוי נשמר בהצלחה",
            "count": len(rows)
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/web/nicknames/restore", methods=["POST"])
def web_nicknames_restore():
    """Restore nicknames from local nicknames.xlsx file."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        backup_path = os.path.join(script_dir, "nicknames.xlsx")

        if not os.path.exists(backup_path):
            return jsonify({"success": False, "error": "קובץ nicknames.xlsx לא נמצא"})

        df = pd.read_excel(backup_path, dtype=str)

        if df.shape[1] < 2:
            return jsonify({"success": False, "error": "פורמט קובץ לא תקין"})

        df.columns = ['formal_name', 'all_names'] + list(df.columns[2:])

        db = get_db()
        cursor = db.cursor()

        # Clear existing nicknames and insert from file
        cursor.execute("DELETE FROM nicknames")

        count = 0
        for _, row in df.iterrows():
            formal_name = str(row['formal_name']).strip() if pd.notna(row['formal_name']) else ""
            all_names = str(row['all_names']).strip() if pd.notna(row['all_names']) else ""

            if formal_name and all_names:
                cursor.execute(
                    "INSERT INTO nicknames (formal_name, all_names) VALUES (?, ?)",
                    (formal_name, all_names)
                )
                count += 1

        db.commit()

        return jsonify({
            "success": True,
            "message": "שחזור בוצע בהצלחה",
            "count": count
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/web/nicknames/edit")
def web_nicknames_edit_page():
    """Serve the nickname edit page."""
    current_user = get_logged_in_user()
    is_admin = int(current_user.get("admin_flag", 0)) == 1 if current_user else False
    return render_template("nickname_edit.html", is_admin=is_admin)


@app.route("/web/nicknames/get")
def web_nicknames_get():
    """Get nicknames for a specific formal name."""
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"found": False, "error": "שם נדרש"})

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT all_names FROM nicknames WHERE formal_name = ?", (name,))
    row = cursor.fetchone()

    if row:
        return jsonify({
            "found": True,
            "formal_name": name,
            "all_names": row[0]
        })
    else:
        return jsonify({
            "found": False,
            "formal_name": name
        })


@app.route("/web/nicknames/save", methods=["POST"])
def web_nicknames_save():
    """Save or update nicknames for a formal name."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON body required"})

    formal_name = data.get("formal_name", "").strip()
    all_names = data.get("all_names", "").strip()

    if not formal_name:
        return jsonify({"success": False, "error": "שם רשמי נדרש"})

    if not all_names:
        return jsonify({"success": False, "error": "כינויים נדרשים"})

    try:
        db = get_db()
        cursor = db.cursor()

        # Check if exists
        cursor.execute("SELECT id FROM nicknames WHERE formal_name = ?", (formal_name,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                "UPDATE nicknames SET all_names = ? WHERE formal_name = ?",
                (all_names, formal_name)
            )
        else:
            cursor.execute(
                "INSERT INTO nicknames (formal_name, all_names) VALUES (?, ?)",
                (formal_name, all_names)
            )

        db.commit()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/web/nicknames/delete", methods=["POST"])
def web_nicknames_delete():
    """Delete nicknames for a formal name."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON body required"})

    formal_name = data.get("formal_name", "").strip()

    if not formal_name:
        return jsonify({"success": False, "error": "שם רשמי נדרש"})

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM nicknames WHERE formal_name = ?", (formal_name,))
        db.commit()

        if cursor.rowcount > 0:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "שם לא נמצא"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    debug_mode = os.environ.get("DEBUG", "true").lower() == "true"
    print(f"Starting phoneinfo server on http://{SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=debug_mode)
