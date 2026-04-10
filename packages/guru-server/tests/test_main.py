from __future__ import annotations

import logging

import pytest


class TestMainArgParsing:
    @pytest.fixture(autouse=True)
    def reset_root_logger(self):
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        yield
        root.handlers = original_handlers
        root.level = original_level

    def test_parse_log_level_flag(self):
        from guru_server.main import _parse_args

        args = _parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_parse_log_file_flag(self):
        from guru_server.main import _parse_args

        args = _parse_args(["--log-file", "/tmp/test.log"])
        assert args.log_file == "/tmp/test.log"

    def test_default_log_level_is_none(self):
        from guru_server.main import _parse_args

        args = _parse_args([])
        assert args.log_level is None

    def test_default_log_file_is_none(self):
        from guru_server.main import _parse_args

        args = _parse_args([])
        assert args.log_file is None
