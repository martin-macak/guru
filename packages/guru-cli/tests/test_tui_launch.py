from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from guru_cli.cli import cli
from guru_cli.tui.app import WorkbenchApp


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


async def test_tui_bindings_dispatch_and_mutate_state():
    app = WorkbenchApp()

    async with app.run_test() as pilot:
        assert app.selected_mode == "investigate"
        assert app.tree_visible is False
        assert app.detail_visible is False

        await pilot.press("2")
        assert app.selected_mode == "graph"

        await pilot.press("ctrl+b")
        assert app.tree_visible is True

        await pilot.press("ctrl+d")
        assert app.detail_visible is True
