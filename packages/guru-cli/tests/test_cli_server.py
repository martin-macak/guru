from __future__ import annotations

from unittest.mock import AsyncMock, patch

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


def test_server_web_open_invokes_backend_url():
    runner = CliRunner()
    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.web_open = AsyncMock(return_value={"opened": True, "url": "http://127.0.0.1:41773"})

        result = runner.invoke(cli, ["server", "web-open"])

    assert result.exit_code == 0
    assert "41773" in result.output


def test_server_web_open_exits_when_web_unavailable():
    runner = CliRunner()
    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.web_open = AsyncMock(return_value={"opened": False, "url": None})

        result = runner.invoke(cli, ["server", "web-open"])

    assert result.exit_code == 1
    assert "Web UI unavailable." in result.output
