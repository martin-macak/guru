from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip @real_neo4j tests unless GURU_REAL_NEO4J=1 is set.

    Mirrors the existing @real_ollama opt-in pattern. Even with a neo4j
    binary on PATH, subprocess startup needs a properly-staged install whose
    conf paths are writable — CI handles that via a docker service; local
    devs opt in when they have a suitable Neo4j reachable.
    """
    if os.environ.get("GURU_REAL_NEO4J") == "1":
        return
    skip = pytest.mark.skip(reason="real_neo4j not enabled (set GURU_REAL_NEO4J=1)")
    for item in items:
        if "real_neo4j" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def real_neo4j_backend(tmp_path: Path):
    from guru_graph.backend import Neo4jBackend
    from guru_graph.config import allocate_free_loopback_port

    port = allocate_free_loopback_port()
    data_dir = tmp_path / "neo4j"
    log_file = tmp_path / "neo4j.log"
    backend = Neo4jBackend(data_dir=data_dir, bolt_port=port, log_file=log_file)
    backend.start()
    try:
        yield backend
    finally:
        backend.stop()
