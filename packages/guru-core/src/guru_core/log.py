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
    daemon: bool = False,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configure logging for all guru packages.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
               Falls back to GURU_LOG_LEVEL env var, then INFO.
        log_file: Optional path for a RotatingFileHandler.
        daemon: When True, suppress the stderr StreamHandler to avoid double-writes.
                In daemon mode the parent process redirects the subprocess stderr fd
                to the same log file, so adding a StreamHandler on top of the
                RotatingFileHandler would write every line twice.
                When False (default, interactive / CLI mode), stderr is always added
                in addition to any log_file so output is visible in the terminal.
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

    # Add stderr handler unless daemon mode is active.
    # daemon=True means the subprocess stderr fd is already redirected to log_file by
    # the parent process (autostart.py), so a StreamHandler would cause double-writes.
    # In all other cases (foreground server, CLI, interactive use) stderr is always
    # included so log output is visible in the terminal even when log_file is set.
    if not daemon:
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
