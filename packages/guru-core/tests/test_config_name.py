from __future__ import annotations

import json
from pathlib import Path

from guru_core.config import resolve_config


def test_name_parsed_from_config(tmp_path: Path):
    """Config with a name field exposes it on GuruConfig."""
    config_file = tmp_path / ".guru.json"
    config_file.write_text(
        json.dumps(
            {
                "name": "my-project",
                "rules": [{"ruleName": "default", "match": {"glob": "**/*.md"}}],
            }
        )
    )
    cfg = resolve_config(project_root=tmp_path)
    assert cfg.name == "my-project"


def test_name_absent_returns_none(tmp_path: Path):
    """Config without name field has name=None."""
    config_file = tmp_path / ".guru.json"
    config_file.write_text(
        json.dumps(
            {
                "rules": [{"ruleName": "default", "match": {"glob": "**/*.md"}}],
            }
        )
    )
    cfg = resolve_config(project_root=tmp_path)
    assert cfg.name is None


def test_name_absent_defaults_none_when_no_config(tmp_path: Path):
    """Default config (no file) has name=None."""
    cfg = resolve_config(project_root=tmp_path)
    assert cfg.name is None


def test_name_from_legacy_flat_array(tmp_path: Path):
    """Legacy flat-array config auto-wraps with name=None."""
    config_file = tmp_path / ".guru.json"
    config_file.write_text(
        json.dumps(
            [
                {"ruleName": "default", "match": {"glob": "**/*.md"}},
            ]
        )
    )
    cfg = resolve_config(project_root=tmp_path)
    assert cfg.name is None
