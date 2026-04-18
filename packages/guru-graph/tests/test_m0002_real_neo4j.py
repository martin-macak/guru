from __future__ import annotations

import pytest

pytestmark = pytest.mark.real_neo4j


def test_m0002_applied_to_empty_neo4j(real_neo4j_backend):
    """ensure_schema(2) runs m0001 + m0002; verify new constraint is installed."""
    real_neo4j_backend.ensure_schema(target_version=2)
    assert real_neo4j_backend.info().schema_version == 2

    result = real_neo4j_backend.execute_read("SHOW CONSTRAINTS YIELD name RETURN name", {})
    names = {row[0] for row in result.rows}
    assert "document_id_unique" in names
    assert "annotation_id_unique" in names


def test_m0002_is_idempotent_on_real_neo4j(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=2)
    real_neo4j_backend.ensure_schema(target_version=2)  # second call is a no-op
    assert real_neo4j_backend.info().schema_version == 2
