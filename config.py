import os
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()


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


# API Configuration
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

# File upload security
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Store processed files temporarily
PROCESSED_FILES = {}

# File cleanup configuration
FILE_EXPIRY_MINUTES = 5
CLEANUP_INTERVAL_SECONDS = 60

# Rate limiter (initialized without app — call limiter.init_app(app) in server.py)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
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
