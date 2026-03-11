import os
import threading
from dotenv import load_dotenv
from flask_limiter import Limiter

load_dotenv()

# Database configuration
DATABASE = os.environ.get("DATABASE", "db/db.db")

# Server configuration
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", "5432"))

# File upload security
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024

# Store processed files temporarily (thread-safe access via lock)
PROCESSED_FILES = {}
processed_files_lock = threading.Lock()

# File cleanup configuration
FILE_EXPIRY_MINUTES = int(os.environ.get("FILE_EXPIRY_MINUTES", "5"))
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "60"))


# Rate limiter key.
# CF-Connecting-IP is only trustworthy when traffic is routed through Cloudflare.
# Set TRUST_CF_IP=true in .env when deployed behind Cloudflare to use it;
# otherwise fall back to the direct remote address (default for safety).
_trust_cf_ip = os.environ.get("TRUST_CF_IP", "false").lower() == "true"


def _get_client_ip():
    from flask import request
    if _trust_cf_ip:
        return request.headers.get("CF-Connecting-IP") or request.remote_addr
    return request.remote_addr


_rate_day = os.environ.get("RATE_LIMIT_DAY", "200 per day")
_rate_hour = os.environ.get("RATE_LIMIT_HOUR", "50 per hour")
# Use RATE_LIMIT_STORAGE_URI=redis://... in production so limits are shared
# across gunicorn workers and survive restarts.  Defaults to in-memory (dev only).
_storage_uri = os.environ.get("RATE_LIMIT_STORAGE_URI", "memory://")
limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[_rate_day, _rate_hour],
    storage_uri=_storage_uri,
    strategy="fixed-window"
)


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_cf_user():
    """Get authenticated user email from Cloudflare Access header."""
    from flask import request
    return request.headers.get("Cf-Access-Authenticated-User-Email")
