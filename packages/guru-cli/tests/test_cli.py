import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from guru_cli.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower() or "." in result.output


def test_init_creates_guru_dir(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (Path(td) / ".guru").is_dir()
        assert "Created .guru/" in result.output


def test_init_with_config(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        config_file = Path(td) / "guru.json"
        assert config_file.is_file()
        config = json.loads(config_file.read_text())
        assert config[0]["ruleName"] == "default"


def test_init_already_initialized(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        (Path(td) / ".guru").mkdir()
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "already initialized" in result.output.lower()


def test_init_creates_mcp_json(runner, tmp_path):
    """guru init creates .mcp.json with guru entry when file doesn't exist."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        mcp_file = Path(td) / ".mcp.json"
        assert mcp_file.is_file()
        mcp = json.loads(mcp_file.read_text())
        assert mcp["mcpServers"]["guru"]["command"] == "guru-mcp"
        assert "Added guru to .mcp.json" in result.output


def test_init_merges_into_existing_mcp_json(runner, tmp_path):
    """guru init preserves existing MCP servers when adding guru."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        mcp_file = Path(td) / ".mcp.json"
        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "other-tool": {"command": "other-tool-mcp"}
            }
        }))
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        mcp = json.loads(mcp_file.read_text())
        assert "other-tool" in mcp["mcpServers"]
        assert "guru" in mcp["mcpServers"]


def test_init_skips_existing_guru_mcp_entry(runner, tmp_path):
    """guru init skips .mcp.json if guru entry already exists."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        mcp_file = Path(td) / ".mcp.json"
        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "guru": {"command": "guru-mcp"}
            }
        }))
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "guru already configured in .mcp.json" in result.output


def test_init_creates_gitignore(runner, tmp_path):
    """guru init creates .gitignore with .guru/ when file doesn't exist."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        gitignore = Path(td) / ".gitignore"
        assert gitignore.is_file()
        assert ".guru/" in gitignore.read_text().splitlines()
        assert "Added .guru/ to .gitignore" in result.output


def test_init_appends_to_existing_gitignore(runner, tmp_path):
    """guru init appends .guru/ to existing .gitignore."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        gitignore = Path(td) / ".gitignore"
        gitignore.write_text("node_modules/\n.env\n")
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        lines = gitignore.read_text().splitlines()
        assert "node_modules/" in lines
        assert ".env" in lines
        assert ".guru/" in lines


def test_init_skips_existing_gitignore_entry(runner, tmp_path):
    """guru init skips .gitignore if .guru/ already present."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        gitignore = Path(td) / ".gitignore"
        gitignore.write_text(".guru/\n")
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert ".guru/ already in .gitignore" in result.output


def test_config_shows_resolved(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        td_path = Path(td)
        (td_path / ".guru").mkdir()
        guru_json = td_path / "guru.json"
        guru_json.write_text(json.dumps([
            {"ruleName": "specs", "match": {"glob": "specs/**/*.md"}, "labels": ["spec"]},
        ]))
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0
        assert "specs" in result.output
