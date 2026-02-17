import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g
from config import (
    DATABASE, SERVER_HOST, SERVER_PORT, PROCESSED_FILES,
    FILE_EXPIRY_MINUTES, CLEANUP_INTERVAL_SECONDS, limiter, get_cf_user,
)
from db import init_db, init_nickname_table, load_nicknames_from_json
from routes.api import api_bp
from routes.web import web_bp
from routes.nicknames import nicknames_bp

# Initialize database on startup
_init_conn = init_db(DATABASE)
init_nickname_table(_init_conn)
load_nicknames_from_json(_init_conn)
_init_conn.close()

# Create Flask app
app = Flask("phoneinfo")
limiter.init_app(app)

# Register blueprints (no url_prefix — keep existing URLs)
app.register_blueprint(api_bp)
app.register_blueprint(web_bp)
app.register_blueprint(nicknames_bp)


# Security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    if request.path.startswith('/web/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response


@app.before_request
def enforce_cf_auth():
    """Require Cloudflare Access authentication on all requests."""
    if request.endpoint == "static" or request.path == "/health":
        return None
    if not get_cf_user():
        return jsonify({"error": "Access denied"}), 403


@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


# Background cleanup for temporary processed files
def cleanup_old_files():
    """Background task to clean up old processed files."""
    while True:
        try:
            time.sleep(CLEANUP_INTERVAL_SECONDS)

            now = datetime.now()
            expired_files = []

            for file_id, file_info in PROCESSED_FILES.items():
                created_time = file_info.get("created")
                if created_time and (now - created_time) > timedelta(minutes=FILE_EXPIRY_MINUTES):
                    expired_files.append(file_id)

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


cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()


if __name__ == "__main__":
    debug_mode = os.environ.get("DEBUG", "true").lower() == "true"
    print(f"Starting phoneinfo server on http://{SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=debug_mode)
