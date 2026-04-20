"""Red-tests for Neo4jBackend connect-only mode.

These are pure unit tests (NOT @real_neo4j) — they verify the architectural
contract that when a bolt_uri is supplied, Neo4jBackend MUST NOT spawn a
neo4j subprocess. The CI path (native test Neo4j or any other external
instance) depends on this
contract.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from guru_graph.backend.neo4j_backend import Neo4jBackend


def test_connect_only_mode_skips_subprocess(tmp_path: Path):
    """With an external bolt_uri, start() must not call start_neo4j()."""
    started = []

    def fake_start_neo4j(**kwargs):
        started.append(kwargs)
        raise AssertionError("start_neo4j must not be called in connect-only mode")

    with (
        patch(
            "guru_graph.backend.neo4j_backend.start_neo4j",
            side_effect=fake_start_neo4j,
        ),
        patch("guru_graph.backend.neo4j_backend.GraphDatabase.driver") as fake_driver,
    ):
        # Prevent real network calls from the fake driver's session/verify.
        fake_driver.return_value.session.return_value.__enter__.return_value.run.return_value.single.return_value = None

        backend = Neo4jBackend(
            data_dir=tmp_path / "data",
            bolt_port=7687,
            log_file=tmp_path / "neo4j.log",
            bolt_uri="bolt://localhost:7687",
        )
        backend.start()

    assert started == [], "start_neo4j was called despite bolt_uri being set"


def test_connect_only_mode_uses_given_bolt_uri(tmp_path: Path):
    """The driver must be constructed with the given bolt_uri verbatim."""
    with (
        patch("guru_graph.backend.neo4j_backend.start_neo4j") as fake_start,
        patch("guru_graph.backend.neo4j_backend.GraphDatabase.driver") as fake_driver,
    ):
        fake_driver.return_value.session.return_value.__enter__.return_value.run.return_value.single.return_value = None

        backend = Neo4jBackend(
            data_dir=tmp_path / "data",
            bolt_port=7687,
            log_file=tmp_path / "neo4j.log",
            bolt_uri="bolt://ci-neo4j:7687",
        )
        backend.start()

    fake_start.assert_not_called()
    fake_driver.assert_called_once()
    args, _kwargs = fake_driver.call_args
    assert args[0] == "bolt://ci-neo4j:7687"


def test_subprocess_mode_still_spawns(tmp_path: Path):
    """Without bolt_uri, start() must still call start_neo4j()."""
    fake_runtime = type("RT", (), {"bolt_uri": "bolt://127.0.0.1:9999", "process": None})()
    with (
        patch(
            "guru_graph.backend.neo4j_backend.start_neo4j",
            return_value=fake_runtime,
        ) as fake_start,
        patch("guru_graph.backend.neo4j_backend.GraphDatabase.driver") as fake_driver,
    ):
        fake_driver.return_value.session.return_value.__enter__.return_value.run.return_value.single.return_value = None

        backend = Neo4jBackend(
            data_dir=tmp_path / "data",
            bolt_port=9999,
            log_file=tmp_path / "neo4j.log",
        )
        backend.start()

    fake_start.assert_called_once()


def test_connect_only_stop_does_not_stop_neo4j(tmp_path: Path):
    """In connect-only mode, stop() closes the driver but does not touch
    an external Neo4j process.
    """
    with (
        patch("guru_graph.backend.neo4j_backend.stop_neo4j") as fake_stop,
        patch("guru_graph.backend.neo4j_backend.GraphDatabase.driver") as fake_driver,
    ):
        fake_driver.return_value.session.return_value.__enter__.return_value.run.return_value.single.return_value = None

        backend = Neo4jBackend(
            data_dir=tmp_path / "data",
            bolt_port=7687,
            log_file=tmp_path / "neo4j.log",
            bolt_uri="bolt://localhost:7687",
        )
        backend.start()
        backend.stop()

    fake_stop.assert_not_called()
    fake_driver.return_value.close.assert_called_once()


@pytest.mark.parametrize("bad_uri", ["", "http://not-bolt", "neo4j"])
def test_connect_only_rejects_non_bolt_uri(tmp_path: Path, bad_uri: str):
    """Guard rails: only bolt:// or neo4j:// schemes are valid for connect-only."""
    with pytest.raises(ValueError):
        Neo4jBackend(
            data_dir=tmp_path / "data",
            bolt_port=7687,
            log_file=tmp_path / "neo4j.log",
            bolt_uri=bad_uri,
        )
