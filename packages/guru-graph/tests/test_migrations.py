from __future__ import annotations

import pytest

from guru_graph.versioning import VersionNegotiationError

pytestmark = pytest.mark.real_neo4j


def test_ensure_schema_applies_m0001(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    assert real_neo4j_backend.info().schema_version == 1


def test_ensure_schema_is_idempotent(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    real_neo4j_backend.ensure_schema(target_version=1)
    assert real_neo4j_backend.info().schema_version == 1


def test_ensure_schema_refuses_downgrade(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    with pytest.raises(VersionNegotiationError):
        real_neo4j_backend.ensure_schema(target_version=0)
