# Gunicorn configuration file for PhoneInfo
# https://docs.gunicorn.org/en/stable/settings.html

import os

# Server Socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = int(os.environ.get("GUNICORN_BACKLOG", "64"))

# Worker Processes
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))  # Single worker: PROCESSED_FILES dict must be shared
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "sync")
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
worker_connections = int(os.environ.get("GUNICORN_WORKER_CONNECTIONS", "1000"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "50"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))

# Logging
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
log_dir = os.environ.get("LOG_DIR", "logs")
accesslog = f"{log_dir}/access.log"
errorlog = f"{log_dir}/error.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

log_max_bytes = int(os.environ.get("LOG_MAX_BYTES", str(100 * 1024 * 1024)))  # 100 MB
log_backup_count = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "access": {
            "format": "%(message)s",
        },
    },
    "handlers": {
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": f"{log_dir}/error.log",
            "maxBytes": log_max_bytes,
            "backupCount": log_backup_count,
            "formatter": "default",
            "encoding": "utf-8",
        },
        "access_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": f"{log_dir}/access.log",
            "maxBytes": log_max_bytes,
            "backupCount": log_backup_count,
            "formatter": "access",
            "encoding": "utf-8",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "gunicorn.error": {
            "handlers": ["error_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "gunicorn.access": {
            "handlers": ["access_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["error_file", "console"],
        "level": "INFO",
    },
}

# Security
limit_request_line = int(os.environ.get("GUNICORN_LIMIT_REQUEST_LINE", "4096"))
limit_request_fields = int(os.environ.get("GUNICORN_LIMIT_REQUEST_FIELDS", "100"))
limit_request_field_size = int(os.environ.get("GUNICORN_LIMIT_REQUEST_FIELD_SIZE", "8190"))

# Process Naming
proc_name = "phoneinfo"

# Server Mechanics
daemon = False  # Don't daemonize (Docker handles this)
pidfile = None
user = None
group = None
tmp_upload_dir = None
