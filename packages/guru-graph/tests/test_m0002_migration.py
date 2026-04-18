from __future__ import annotations

import pytest

from guru_graph.migrations.m0002_artifact_schema import apply as apply_m0002
from guru_graph.testing.fake_backend import FakeBackend
from guru_graph.versioning import VersionNegotiationError


def test_m0002_apply_runs_ddl_and_ensure_schema_bumps_version():
    backend = FakeBackend(_schema_version=1)
    backend.start()
    apply_m0002(backend)  # DDL is a no-op for FakeBackend but must not raise
    backend.ensure_schema(target_version=2)
    assert backend.info().schema_version == 2


def test_m0002_rerun_is_idempotent_on_fake():
    backend = FakeBackend(_schema_version=2)
    backend.start()
    # Re-apply against a v2 fake is safe (IF NOT EXISTS Cypher;
    # FakeBackend.execute is a stub).
    apply_m0002(backend)
    apply_m0002(backend)
    backend.ensure_schema(target_version=2)
    assert backend.info().schema_version == 2


def test_ensure_schema_refuses_downgrade_v3_to_v2():
    backend = FakeBackend(_schema_version=3)
    backend.start()
    with pytest.raises(VersionNegotiationError):
        backend.ensure_schema(target_version=2)


def test_m0002_is_registered_in_migrations():
    from guru_graph.migrations import MIGRATIONS

    versions = [v for v, _fn in MIGRATIONS]
    assert versions == sorted(versions)
    assert 2 in versions
