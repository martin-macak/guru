from __future__ import annotations

import json
from pathlib import Path

from guru_cli.skills_install import install_skill, update_skill


def test_install_writes_all_files_and_manifest(tmp_path: Path):
    install_skill(tmp_path)
    dest = tmp_path / ".claude" / "skills" / "guru-knowledge-base"
    assert (dest / "SKILL.md").exists()
    for n in ("model", "discovery", "curation", "annotation-shape", "linking-patterns", "orphans"):
        assert (dest / "references" / f"{n}.md").exists()
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    assert "files" in manifest
    assert manifest["files"]["SKILL.md"]  # sha256
    agents = tmp_path / ".agents" / "skills" / "guru-knowledge-base"
    assert agents.is_symlink() or agents.exists()


def test_update_noop_when_unchanged(tmp_path: Path):
    install_skill(tmp_path)
    changed = update_skill(tmp_path)
    assert changed == []


def test_update_overwrites_when_shipped_changed_but_user_unmodified(tmp_path: Path, monkeypatch):
    install_skill(tmp_path)
    # Simulate user kept the file intact while the shipped version changes
    dest = tmp_path / ".claude" / "skills" / "guru-knowledge-base"
    # We pretend the on-disk manifest is older by editing its hash for SKILL.md
    manifest_path = dest / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["SKILL.md"] = "deadbeef" * 8
    manifest_path.write_text(json.dumps(manifest))
    changed = update_skill(tmp_path)
    assert "SKILL.md" in changed


def test_update_skips_user_modified_file(tmp_path: Path):
    install_skill(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "SKILL.md"
    skill.write_text(skill.read_text() + "\n\n## Custom section\n")
    changed = update_skill(tmp_path)
    assert "SKILL.md" not in changed


def test_update_force_overwrites_and_backs_up(tmp_path: Path):
    install_skill(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "SKILL.md"
    custom_content = "custom\n"
    skill.write_text(custom_content)
    changed = update_skill(tmp_path, force=True)
    assert "SKILL.md" in changed
    backups = list(skill.parent.glob("SKILL.md.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == custom_content


def test_update_dry_run_writes_nothing(tmp_path: Path):
    install_skill(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "SKILL.md"
    # Pretend manifest mismatch
    manifest = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "MANIFEST.json"
    m = json.loads(manifest.read_text())
    m["files"]["SKILL.md"] = "deadbeef" * 8
    manifest.write_text(json.dumps(m))
    mtime_before = skill.stat().st_mtime
    changed = update_skill(tmp_path, dry_run=True)
    assert "SKILL.md" in changed
    assert skill.stat().st_mtime == mtime_before
