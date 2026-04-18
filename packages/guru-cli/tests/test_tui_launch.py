from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from guru_cli.cli import cli


def test_bare_guru_launches_tui():
    runner = CliRunner()
    with patch("guru_cli.tui.app.run_tui") as mock_run_tui:
        result = runner.invoke(cli, [])
    assert result.exit_code == 0
    mock_run_tui.assert_called_once_with()


def test_guru_tui_launches_same_entrypoint():
    runner = CliRunner()
    with patch("guru_cli.tui.app.run_tui") as mock_run_tui:
        result = runner.invoke(cli, ["tui"])
    assert result.exit_code == 0
    mock_run_tui.assert_called_once_with()
