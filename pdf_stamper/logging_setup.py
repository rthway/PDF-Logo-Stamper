"""Structured application logging.

Logs go to a rotating file under %LOCALAPPDATA% so support can ask a user for
one file. File *paths* and page counts are logged; document contents never are.
Set PDFSTAMPER_DEBUG=1 for DEBUG level and console output.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

APP_DIR_NAME = "PDF Logo Stamper"
_configured = False


def log_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME, "logs")
    os.makedirs(path, exist_ok=True)
    return path


def log_file():
    return os.path.join(log_dir(), "app.log")


def setup_logging():
    """Configure logging once; safe to call repeatedly. Returns the log path."""
    global _configured
    if _configured:
        return log_file()

    debug = os.environ.get("PDFSTAMPER_DEBUG") == "1"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-22s %(message)s", "%Y-%m-%d %H:%M:%S")

    try:
        handler = RotatingFileHandler(log_file(), maxBytes=1_000_000,
                                      backupCount=3, encoding="utf-8")
        handler.setFormatter(fmt)
        root.addHandler(handler)
    except OSError:
        pass  # a read-only profile must not stop the app from starting

    if debug or sys.stderr and not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.setLevel(logging.DEBUG if debug else logging.WARNING)
        root.addHandler(console)

    _configured = True
    logging.getLogger(__name__).info("Logging started (debug=%s)", debug)
    return log_file()


def get_logger(name):
    return logging.getLogger(name)
