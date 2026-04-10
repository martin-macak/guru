from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_GURU_HANDLER_ATTR = "_guru_logging"


def setup_logging(
    level: str | None = None,
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configure logging for all guru packages.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
               Falls back to GURU_LOG_LEVEL env var, then INFO.
        log_file: Optional path for a RotatingFileHandler.
        max_bytes: Max log file size before rotation (default 10MB).
        backup_count: Number of rotated files to keep (default 3).
    """
    root = logging.getLogger()

    # Remove any handlers we previously added (idempotent)
    root.handlers = [h for h in root.handlers if not getattr(h, _GURU_HANDLER_ATTR, False)]

    # Resolve level: explicit arg > env var > INFO
    if level is None:
        level = os.environ.get("GURU_LOG_LEVEL", "INFO")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Always add stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    setattr(stderr_handler, _GURU_HANDLER_ATTR, True)
    root.addHandler(stderr_handler)

    # Optionally add rotating file handler
    if log_file:
        file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
        file_handler.setFormatter(formatter)
        setattr(file_handler, _GURU_HANDLER_ATTR, True)
        root.addHandler(file_handler)
