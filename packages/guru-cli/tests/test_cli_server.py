from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from guru_cli.cli import cli


class TestServerStartFlags:
    def test_foreground_flag_accepted(self):
        runner = CliRunner()
        with (
            patch("guru_cli.cli.find_guru_root") as mock_find,
            patch("guru_cli.cli._run_foreground") as mock_fg,
        ):
            mock_find.return_value = "/tmp/fake"
            runner.invoke(cli, ["server", "start", "--foreground"])
            mock_fg.assert_called_once()

    def test_log_level_flag_accepted(self):
        runner = CliRunner()
        with (
            patch("guru_cli.cli.find_guru_root") as mock_find,
            patch("guru_cli.cli.ensure_server"),
        ):
            mock_find.return_value = "/tmp/fake"
            result = runner.invoke(cli, ["server", "start", "--log-level", "DEBUG"])
            assert "no such option" not in (result.output or "").lower()

    def test_log_file_flag_accepted(self):
        runner = CliRunner()
        with (
            patch("guru_cli.cli.find_guru_root") as mock_find,
            patch("guru_cli.cli.ensure_server"),
        ):
            mock_find.return_value = "/tmp/fake"
            result = runner.invoke(cli, ["server", "start", "--log-file", "/tmp/test.log"])
            assert "no such option" not in (result.output or "").lower()

    def test_daemon_mode_passes_log_level_to_ensure_server(self):
        runner = CliRunner()
        with (
            patch("guru_cli.cli.find_guru_root") as mock_find,
            patch("guru_cli.cli.ensure_server") as mock_ensure,
        ):
            mock_find.return_value = "/tmp/fake"
            runner.invoke(cli, ["server", "start", "--log-level", "DEBUG"])
            mock_ensure.assert_called_once()
            _, kwargs = mock_ensure.call_args
            assert kwargs.get("log_level") == "DEBUG"
