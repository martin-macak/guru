from __future__ import annotations

import socket
from pathlib import Path

import pytest

from guru_graph.config import GraphPaths, allocate_free_loopback_port


def test_graph_paths_produces_all_locations(tmp_path: Path):
    paths = GraphPaths.for_test(base=tmp_path)
    assert paths.socket.parent == tmp_path
    assert paths.data_dir.is_relative_to(tmp_path)
    assert paths.pid_file.is_relative_to(tmp_path)
    assert paths.lock_file.is_relative_to(tmp_path)
    assert paths.log_file.is_relative_to(tmp_path)


def test_graph_paths_ensure_dirs(tmp_path: Path):
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    assert paths.data_dir.exists()
    assert paths.pid_file.parent.exists()


def test_graph_paths_default_respects_platform():
    paths = GraphPaths.default()
    assert "guru" in str(paths.data_dir).lower()
    assert paths.socket.name == "graph.sock"


@pytest.mark.compat_socket
def test_allocate_free_port_returns_usable():
    port = allocate_free_loopback_port()
    assert 1024 <= port <= 65535
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()
