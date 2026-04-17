"""GURU_GRAPH_HOME env override.

Production path layout is platform-specific (macOS uses Library/, Linux uses
XDG). Tests and containerized deployments need a single env var that
overrides both branches so all graph state lands in one controlled
directory. This is essential for local BDD reproduction on macOS where the
sandbox may block writes to ~/Library/Application Support/.
"""

from __future__ import annotations

import os
from pathlib import Path

from guru_graph.config import GraphPaths


def test_env_override_points_all_paths_under_guru_graph_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GURU_GRAPH_HOME", str(tmp_path))
    paths = GraphPaths.default()
    assert paths.socket.is_relative_to(tmp_path)
    assert paths.data_dir.is_relative_to(tmp_path)
    assert paths.pid_file.is_relative_to(tmp_path)
    assert paths.lock_file.is_relative_to(tmp_path)
    assert paths.log_file.is_relative_to(tmp_path)


def test_env_override_is_absent_by_default(monkeypatch):
    monkeypatch.delenv("GURU_GRAPH_HOME", raising=False)
    GraphPaths.default()  # must not raise
    assert "GURU_GRAPH_HOME" not in os.environ


def test_env_override_with_empty_string_is_ignored(tmp_path: Path, monkeypatch):
    """Empty GURU_GRAPH_HOME should fall back to platform defaults."""
    monkeypatch.setenv("GURU_GRAPH_HOME", "")
    paths = GraphPaths.default()
    # Whatever the default is, it should not be the empty string.
    assert paths.socket != Path("graph.sock")
