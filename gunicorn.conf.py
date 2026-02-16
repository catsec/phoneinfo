# Gunicorn configuration file for PhoneInfo
# https://docs.gunicorn.org/en/stable/settings.html

import os

# Server Socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = 64

# Worker Processes
workers = 2  # For 3 concurrent users, 2 workers is plenty
worker_class = "sync"  # sync workers are fine for this workload
worker_connections = 1000
max_requests = 1000  # Restart workers after 1000 requests (prevents memory leaks)
max_requests_jitter = 50
timeout = 120  # 2 minutes timeout for long-running requests
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

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
