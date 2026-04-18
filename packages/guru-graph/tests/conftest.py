from __future__ import annotations

import contextlib
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
    """Real Neo4j backend for @real_neo4j tests.

    If `GURU_NEO4J_BOLT_URI` is set, connect-only mode is used (CI + any
    docker-based setup). Otherwise fall back to subprocess mode, which
    requires a `neo4j` binary on PATH whose conf we can override.
    """
    from guru_graph.backend import Neo4jBackend
    from guru_graph.config import allocate_free_loopback_port

    external_uri = os.environ.get("GURU_NEO4J_BOLT_URI") or None
    port = allocate_free_loopback_port()
    data_dir = tmp_path / "neo4j"
    log_file = tmp_path / "neo4j.log"
    backend = Neo4jBackend(
        data_dir=data_dir,
        bolt_port=port,
        log_file=log_file,
        bolt_uri=external_uri,
    )
    backend.start()
    # Connect-only mode shares DB state across tests — wipe before each.
    if external_uri is not None:
        backend.execute("MATCH (n) DETACH DELETE n", {})
        constraints = backend.execute("SHOW CONSTRAINTS YIELD name RETURN name", {})
        for row in constraints.rows:
            with contextlib.suppress(Exception):
                backend.execute(f"DROP CONSTRAINT `{row[0]}` IF EXISTS", {})
        # `type <> 'LOOKUP'` filters out Neo4j's built-in lookup indexes
        # (`node_label_lookup_index`, `relationship_type_lookup_index`) which
        # can't be dropped.
        indexes = backend.execute(
            "SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name", {}
        )
        for row in indexes.rows:
            with contextlib.suppress(Exception):
                backend.execute(f"DROP INDEX `{row[0]}` IF EXISTS", {})
        # Reset cached schema_version since we just wiped _Meta.
        backend._schema_version = 0
    try:
        yield backend
    finally:
        backend.stop()
