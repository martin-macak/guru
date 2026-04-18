"""resolve_config() must preserve graph + name when merging global + local.

The merge branch in resolve_config used to construct `GuruConfig(version=1,
rules=merged_rules)`, silently dropping the `graph` and `name` fields from
the global config. Result: a user with `graph.enabled=true` in
~/.config/guru/config.json plus any local .guru.json got graph disabled
in the resolved config, with no error to tell them.
"""

from __future__ import annotations

import json
from pathlib import Path

from guru_core.config import resolve_config


def _write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_merge_preserves_graph_from_global(tmp_path: Path):
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(
        global_dir / "config.json",
        {"version": 1, "rules": [], "graph": {"enabled": True}},
    )
    _write_config(
        project / ".guru.json",
        {"version": 1, "rules": [{"ruleName": "docs", "match": {"glob": "*.md"}}]},
    )
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.graph is not None
    assert cfg.graph.enabled is True
    assert any(r.rule_name == "docs" for r in cfg.rules)


def test_merge_preserves_name_from_global(tmp_path: Path):
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(
        global_dir / "config.json",
        {"version": 1, "name": "global-kb", "rules": []},
    )
    _write_config(
        project / ".guru.json",
        {"version": 1, "rules": [{"ruleName": "docs", "match": {"glob": "*.md"}}]},
    )
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.name == "global-kb"


def test_local_graph_overrides_global_graph(tmp_path: Path):
    """Local config's graph field overrides global when both set."""
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(
        global_dir / "config.json",
        {"version": 1, "rules": [], "graph": {"enabled": False}},
    )
    _write_config(
        project / ".guru.json",
        {"version": 1, "rules": [], "graph": {"enabled": True}},
    )
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.graph is not None
    assert cfg.graph.enabled is True


def test_local_name_overrides_global_name(tmp_path: Path):
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(
        global_dir / "config.json",
        {"version": 1, "name": "global", "rules": []},
    )
    _write_config(
        project / ".guru.json",
        {"version": 1, "name": "local", "rules": []},
    )
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.name == "local"


def test_merge_with_no_graph_in_either_leaves_graph_none(tmp_path: Path):
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(global_dir / "config.json", {"version": 1, "rules": []})
    _write_config(project / ".guru.json", {"version": 1, "rules": []})
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.graph is None
