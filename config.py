import os
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

# Database configuration
DATABASE = os.environ.get("DATABASE", "db/db.db")

# Server configuration
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", "5001"))

# File upload security
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024

# Store processed files temporarily
PROCESSED_FILES = {}

# File cleanup configuration
FILE_EXPIRY_MINUTES = int(os.environ.get("FILE_EXPIRY_MINUTES", "5"))
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "60"))

# Rate limiter (initialized without app — call limiter.init_app(app) in server.py)
_rate_day = os.environ.get("RATE_LIMIT_DAY", "200 per day")
_rate_hour = os.environ.get("RATE_LIMIT_HOUR", "50 per hour")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_rate_day, _rate_hour],
    storage_uri="memory://",
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
