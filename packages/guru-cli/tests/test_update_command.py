"""Tests for the `guru update` Click command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from guru_cli.commands.update import update_cmd
from guru_cli.skills_install import install_skill


def test_update_reports_no_changes_on_fresh_install(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        install_skill(Path.cwd())
        result = runner.invoke(update_cmd, [])
    assert result.exit_code == 0, result.output
    assert "already up to date" in result.output


def test_update_dry_run_reports_would_update(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        install_skill(Path.cwd())
        # Tamper the manifest so update sees the file as needing reconciliation.
        manifest_path = Path(".claude/skills/guru-knowledge-base/MANIFEST.json")
        m = json.loads(manifest_path.read_text())
        m["files"]["SKILL.md"] = "deadbeef" * 8
        manifest_path.write_text(json.dumps(m))
        result = runner.invoke(update_cmd, ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would update: SKILL.md" in result.output


def test_update_real_run_reports_updated(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        install_skill(Path.cwd())
        manifest_path = Path(".claude/skills/guru-knowledge-base/MANIFEST.json")
        m = json.loads(manifest_path.read_text())
        m["files"]["SKILL.md"] = "deadbeef" * 8
        manifest_path.write_text(json.dumps(m))
        result = runner.invoke(update_cmd, [])
    assert result.exit_code == 0, result.output
    assert "updated: SKILL.md" in result.output


def test_update_force_overwrites_user_edit(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        install_skill(Path.cwd())
        skill = Path(".claude/skills/guru-knowledge-base/SKILL.md")
        skill.write_text("user-customised content\n")
        result = runner.invoke(update_cmd, ["--force"])
    assert result.exit_code == 0, result.output
    assert "updated: SKILL.md" in result.output


def test_init_installs_skill(tmp_path: Path):
    """End-to-end smoke: `guru init` materialises the skill tree."""
    from guru_cli.cli import init

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(init, [])
        assert result.exit_code == 0, result.output
        assert "installed skill" in result.output
        assert Path(".claude/skills/guru-knowledge-base/SKILL.md").exists()
        assert Path(".claude/skills/guru-knowledge-base/MANIFEST.json").exists()
        # .agents symlink (or copy on Windows) should also be in place.
        agents = Path(".agents/skills/guru-knowledge-base")
        assert agents.exists() or agents.is_symlink()
