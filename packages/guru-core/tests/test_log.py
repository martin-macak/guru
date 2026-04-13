from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

import pytest

from guru_core.log import _GURU_HANDLER_ATTR, setup_logging

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _guru_stream_handlers(root: logging.Logger) -> list[logging.Handler]:
    """Return only StreamHandlers (not FileHandlers) added by setup_logging."""
    return [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        and getattr(h, _GURU_HANDLER_ATTR, False)
    ]


def _guru_file_handlers(root: logging.Logger) -> list[logging.Handler]:
    """Return only FileHandlers added by setup_logging."""
    return [
        h
        for h in root.handlers
        if isinstance(h, logging.FileHandler) and getattr(h, _GURU_HANDLER_ATTR, False)
    ]


class TestSetupLogging:
    @pytest.fixture(autouse=True)
    def reset_root_logger(self):
        """Remove all handlers added during a test."""
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        yield
        root.handlers = original_handlers
        root.level = original_level

    def test_default_level_is_info(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_level_override(self):
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_stderr_handler_added_when_no_log_file(self):
        """stderr StreamHandler is added in interactive / CLI mode (no log file)."""
        setup_logging()
        root = logging.getLogger()
        assert len(_guru_stream_handlers(root)) == 1

    def test_file_handler_added_when_log_file_provided(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        setup_logging(log_file=log_file)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 10 * 1024 * 1024
        assert file_handlers[0].backupCount == 3

    def test_no_file_handler_when_log_file_not_provided(self):
        setup_logging()
        root = logging.getLogger()
        assert len(_guru_file_handlers(root)) == 0

    def test_log_format(self):
        setup_logging()
        root = logging.getLogger()
        guru_handlers = [h for h in root.handlers if getattr(h, _GURU_HANDLER_ATTR, False)]
        assert guru_handlers[-1].formatter._fmt == LOG_FORMAT

    def test_writes_to_log_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logging(level="INFO", log_file=str(log_file))
        logger = logging.getLogger("test.writes")
        logger.info("hello from test")
        # Flush handlers
        for h in logging.getLogger().handlers:
            h.flush()
        content = log_file.read_text()
        assert "hello from test" in content

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("GURU_LOG_LEVEL", "WARNING")
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_explicit_level_overrides_env_var(self, monkeypatch):
        monkeypatch.setenv("GURU_LOG_LEVEL", "WARNING")
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_idempotent_no_duplicate_handlers(self):
        setup_logging()
        setup_logging()
        root = logging.getLogger()
        assert len(_guru_stream_handlers(root)) == 1

    def test_no_stderr_handler_when_log_file_provided(self, tmp_path):
        """When log_file is given (daemon mode), no stderr StreamHandler is added.

        The subprocess redirect already captures stderr for early crashes.
        Adding a StreamHandler on top would cause every line to be written twice:
        once via RotatingFileHandler and once via StreamHandler→stderr fd→same file.
        """
        log_file = str(tmp_path / "server.log")
        setup_logging(log_file=log_file)
        root = logging.getLogger()
        assert len(_guru_stream_handlers(root)) == 0
