import csv
import io
import logging
import os
from logging.handlers import TimedRotatingFileHandler


LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "30"))

HEADER = "datetime,user,action,filename,phone,me_api_call,sync_api_call,me_cache,sync_cache,me_result,sync_result"

_app_logger = None


def get_app_logger():
    """Get or create the application event logger."""
    global _app_logger
    if _app_logger is not None:
        return _app_logger

    os.makedirs(LOG_DIR, exist_ok=True)

    log_path = os.path.join(LOG_DIR, "app.log")

    _app_logger = logging.getLogger("phoneinfo.app")
    _app_logger.setLevel(logging.INFO)
    _app_logger.propagate = False

    handler = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    _app_logger.addHandler(handler)

    # Write CSV header if file is new or empty
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        _app_logger.info(HEADER)

    return _app_logger


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
    Log an application event.

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
