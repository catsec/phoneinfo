# Gunicorn configuration file for PhoneInfo
# https://docs.gunicorn.org/en/stable/settings.html

import os

# Server Socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = 64

# Worker Processes
workers = 1  # Single worker: PROCESSED_FILES dict must be shared across requests
worker_class = "sync"  # sync workers are fine for this workload
threads = 8  # Handle concurrent requests via threads
worker_connections = 1000
max_requests = 1000  # Restart workers after 1000 requests (prevents memory leaks)
max_requests_jitter = 50
timeout = 120  # 2 minutes timeout for long-running requests
graceful_timeout = 30
keepalive = 5

# Logging
loglevel = "info"
accesslog = "/app/logs/access.log"
errorlog = "/app/logs/error.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Log rotation: daily files, configurable retention
log_retention_days = int(os.environ.get('LOG_RETENTION_DAYS', '30'))

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
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": "/app/logs/error.log",
            "when": "midnight",
            "interval": 1,
            "backupCount": log_retention_days,
            "formatter": "default",
            "encoding": "utf-8",
        },
        "access_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": "/app/logs/access.log",
            "when": "midnight",
            "interval": 1,
            "backupCount": log_retention_days,
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
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Process Naming
proc_name = "phoneinfo"

# Server Mechanics
daemon = False  # Don't daemonize (Docker handles this)
pidfile = None  # No pidfile needed in Docker
user = None     # Run as current user (Docker handles this)
group = None
tmp_upload_dir = None

# SSL (configure if needed)
# keyfile = None
# certfile = None
