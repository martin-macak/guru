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
    assert "0.1.0" in result.output


def test_init_creates_guru_dir(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (Path(td) / ".guru").is_dir()
        assert "Initialized" in result.output


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
