import csv
import io
import logging
import os
from logging.handlers import TimedRotatingFileHandler


LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "90"))

APP_HEADER = "datetime,user,action,filename,phone,me_api_call,sync_api_call,me_cache,sync_cache,me_result,sync_result"
AUDIT_HEADER = "datetime,user,action,target_user,detail"

_app_logger = None
_audit_logger = None


def _init_logger(name, filename, header):
    """Create a rotating file logger with CSV header."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, filename)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    # Write CSV header if file is new or empty
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        logger.info(header)

    return logger


def get_app_logger():
    """Get or create the application event logger (queries/file processing)."""
    global _app_logger
    if _app_logger is None:
        _app_logger = _init_logger("phoneinfo.app", "app.log", APP_HEADER)
    return _app_logger


def get_audit_logger():
    """Get or create the audit logger (auth/admin events)."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = _init_logger("phoneinfo.audit", "audit.log", AUDIT_HEADER)
    return _audit_logger


def _format_csv_line(fields):
    """Format a list of fields as a CSV line."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(fields)
    return buf.getvalue().rstrip("\r\n")


def log_event(user, action, phone, filename="",
              me_api_call=False, sync_api_call=False,
              me_cache=False, sync_cache=False,
              me_result="", sync_result="",
              datetime_str=""):
    """
    Log a query/file processing event to app.log.

    Fields: datetime, user, action, filename, phone,
            me_api_call, sync_api_call, me_cache, sync_cache,
            me_result, sync_result
    """
    logger = get_app_logger()
    line = _format_csv_line([
        datetime_str,
        user,
        action,
        filename,
        phone,
        me_api_call,
        sync_api_call,
        me_cache,
        sync_cache,
        me_result,
        sync_result,
    ])
    logger.info(line)


def log_audit(user, action, target_user="", detail="", datetime_str=""):
    """
    Log an auth/admin event to audit.log.

    Actions: login, login_failed, login_locked, logout,
             user_create, user_delete, password_reset, user_update
    """
    logger = get_audit_logger()
    line = _format_csv_line([
        datetime_str,
        user,
        action,
        target_user,
        detail,
    ])
    logger.info(line)
