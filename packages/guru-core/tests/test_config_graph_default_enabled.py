"""Graph is enabled by default.

Users shouldn't have to edit ~/.config/guru/config.json to get the graph
plugin running — the default contract is "on, with silent degrade if the
daemon/Neo4j isn't available". Opt-OUT by setting graph.enabled=false.
"""

from __future__ import annotations

import json
from pathlib import Path

from guru_core.config import resolve_config
from guru_core.types import GraphConfig, GuruConfig


def _write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_graph_config_enabled_defaults_to_true():
    """GraphConfig() with no args must be enabled."""
    assert GraphConfig().enabled is True


def test_guru_config_graph_defaults_to_enabled_graph_config():
    """GuruConfig() must carry a GraphConfig with enabled=True,
    not None — so `cfg.graph.enabled` is truthy without caller guarding.
    """
    cfg = GuruConfig()
    assert cfg.graph is not None
    assert cfg.graph.enabled is True


def test_resolve_config_with_no_configs_returns_enabled(tmp_path: Path):
    """Fresh install (no global, no local) must have graph enabled."""
    cfg = resolve_config(project_root=tmp_path / "proj", global_config_dir=tmp_path / "global")
    assert cfg.graph is not None
    assert cfg.graph.enabled is True


def test_resolve_config_opt_out_via_global(tmp_path: Path):
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(
        global_dir / "config.json",
        {"version": 1, "rules": [], "graph": {"enabled": False}},
    )
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.graph is not None
    assert cfg.graph.enabled is False


def test_resolve_config_opt_out_via_local(tmp_path: Path):
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(
        project / ".guru.json",
        {"version": 1, "rules": [], "graph": {"enabled": False}},
    )
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.graph is not None
    assert cfg.graph.enabled is False


def test_existing_local_config_without_graph_gets_default_enabled(tmp_path: Path):
    """Backward compat: user with a legacy .guru.json that has no `graph`
    field still gets graph enabled (the default kicks in)."""
    global_dir = tmp_path / "global"
    project = tmp_path / "proj"
    _write_config(
        project / ".guru.json",
        {"version": 1, "rules": [{"ruleName": "x", "match": {"glob": "*.md"}}]},
    )
    cfg = resolve_config(project_root=project, global_config_dir=global_dir)
    assert cfg.graph is not None
    assert cfg.graph.enabled is True
