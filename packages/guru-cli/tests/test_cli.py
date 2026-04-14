import json
from pathlib import Path

import click
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
        config_file = Path(td) / ".guru.json"
        assert config_file.is_file()
        config = json.loads(config_file.read_text())
        assert isinstance(config, dict)
        assert config["version"] == 1
        assert config["rules"][0]["ruleName"] == "default"


def test_init_with_legacy_guru_json(runner, tmp_path):
    """guru init creates .guru.json and warns about legacy guru.json."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        legacy = Path(td) / "guru.json"
        legacy.write_text(json.dumps([{"ruleName": "old", "match": {"glob": "**/*.md"}}]))
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "legacy guru.json" in result.output
        # .guru.json is created; legacy file is untouched
        assert (Path(td) / ".guru.json").exists()
        assert legacy.is_file()


def test_init_warns_about_legacy_even_when_dot_guru_json_exists(runner, tmp_path):
    """guru init warns about legacy guru.json even when .guru.json already exists."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        dot_guru_json = Path(td) / ".guru.json"
        dot_guru_json.write_text(
            json.dumps([{"ruleName": "existing", "match": {"glob": "**/*.md"}}])
        )
        legacy = Path(td) / "guru.json"
        legacy.write_text(json.dumps([{"ruleName": "old", "match": {"glob": "**/*.md"}}]))
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert ".guru.json already exists, skipping." in result.output
        assert "legacy guru.json" in result.output


def test_init_skips_existing_dot_guru_json(runner, tmp_path):
    """guru init skips .guru.json if it already exists."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        dot_guru_json = Path(td) / ".guru.json"
        dot_guru_json.write_text(
            json.dumps([{"ruleName": "existing", "match": {"glob": "**/*.md"}}])
        )
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert ".guru.json already exists, skipping." in result.output


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
        mcp_file.write_text(
            json.dumps({"mcpServers": {"other-tool": {"command": "other-tool-mcp"}}})
        )
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        mcp = json.loads(mcp_file.read_text())
        assert "other-tool" in mcp["mcpServers"]
        assert "guru" in mcp["mcpServers"]


def test_init_skips_existing_guru_mcp_entry(runner, tmp_path):
    """guru init skips .mcp.json if guru entry already exists."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        mcp_file = Path(td) / ".mcp.json"
        mcp_file.write_text(json.dumps({"mcpServers": {"guru": {"command": "guru-mcp"}}}))
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
        guru_json = td_path / ".guru.json"
        guru_json.write_text(
            json.dumps(
                [
                    {"ruleName": "specs", "match": {"glob": "specs/**/*.md"}, "labels": ["spec"]},
                ]
            )
        )
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0
        assert "specs" in result.output


def test_config_reads_legacy_guru_json(runner, tmp_path):
    """guru config falls back to legacy guru.json when .guru.json is absent."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        td_path = Path(td)
        (td_path / ".guru").mkdir()
        legacy = td_path / "guru.json"
        legacy.write_text(
            json.dumps(
                [
                    {"ruleName": "legacy", "match": {"glob": "legacy/**/*.md"}},
                ]
            )
        )
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0
        assert "legacy" in result.output


def test_cache_info_command(tmp_path, monkeypatch):
    """guru cache info calls client.cache_info() and prints the result."""
    from unittest.mock import AsyncMock, patch

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    fake_stats = {
        "path": "/tmp/embeddings.db",
        "total_entries": 42,
        "total_bytes": 1024,
        "by_model": {"nomic-embed-text": 42},
        "last_job_hits": None,
        "last_job_misses": None,
        "last_job_hit_rate": None,
    }
    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.cache_info = AsyncMock(return_value=fake_stats)
        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "info"])
        assert result.exit_code == 0
        assert "42" in result.output
        assert "nomic-embed-text" in result.output


def test_cache_clear_command_with_yes(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.cache_clear = AsyncMock(return_value={"deleted": 7})
        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "clear", "--yes"])
        assert result.exit_code == 0
        assert "7" in result.output


def test_cache_prune_command_with_yes(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.cache_prune = AsyncMock(return_value={"deleted": 3})
        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "prune", "--older-than", "30d", "--yes"])
        assert result.exit_code == 0
        assert "3" in result.output


def test_parse_duration_supports_d_w_h_m():
    from guru_cli.cli import _parse_duration_to_ms

    assert _parse_duration_to_ms("30d") == 30 * 24 * 3600 * 1000
    assert _parse_duration_to_ms("2w") == 14 * 24 * 3600 * 1000
    assert _parse_duration_to_ms("6h") == 6 * 3600 * 1000
    assert _parse_duration_to_ms("15m") == 15 * 60 * 1000


def test_parse_duration_rejects_bad_input():
    import pytest

    from guru_cli.cli import _parse_duration_to_ms

    with pytest.raises(click.BadParameter):
        _parse_duration_to_ms("30days")
    with pytest.raises(click.BadParameter):
        _parse_duration_to_ms("abc")


def test_server_status_prints_cache_block(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    fake_status = {
        "server_running": True,
        "document_count": 5,
        "chunk_count": 50,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "cache": {
            "path": "/tmp/embeddings.db",
            "total_entries": 25,
            "total_bytes": 5000,
            "by_model": {"nomic-embed-text": 25},
            "last_job_hits": 10,
            "last_job_misses": 15,
            "last_job_hit_rate": 0.4,
        },
    }
    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.status = AsyncMock(return_value=fake_status)
        runner = CliRunner()
        result = runner.invoke(cli, ["server", "status"])
        assert result.exit_code == 0
        assert "Cache:" in result.output
        assert "25" in result.output
        assert "10 hits" in result.output or "10" in result.output
