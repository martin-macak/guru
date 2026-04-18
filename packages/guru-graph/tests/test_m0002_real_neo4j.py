from __future__ import annotations

import pytest

pytestmark = pytest.mark.real_neo4j


def test_m0002_applied_to_empty_neo4j(real_neo4j_backend):
    """ensure_schema(2) runs m0001 + m0002; verify new constraint is installed."""
    real_neo4j_backend.ensure_schema(target_version=2)
    assert real_neo4j_backend.info().schema_version == 2

    result = real_neo4j_backend.execute_read("SHOW CONSTRAINTS YIELD name RETURN name", {})
    names = {row[0] for row in result.rows}
    expected = {
        "document_id_unique",
        "module_id_unique",
        "class_id_unique",
        "function_id_unique",
        "method_id_unique",
        "oas_spec_id_unique",
        "oas_op_id_unique",
        "oas_schema_id_unique",
        "md_section_id_unique",
        "annotation_id_unique",
    }
    assert expected <= names, f"missing constraints: {expected - names}"

    idx_result = real_neo4j_backend.execute_read("SHOW INDEXES YIELD name RETURN name", {})
    idx_names = {row[0] for row in idx_result.rows}
    expected_indexes = {
        "document_kb_name",
        "document_language",
        "annotation_kind",
        "annotation_author",
        "module_qualname",
        "class_qualname",
        "function_qualname",
        "method_qualname",
    }
    assert expected_indexes <= idx_names, f"missing indexes: {expected_indexes - idx_names}"


def test_m0002_is_idempotent_on_real_neo4j(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=2)
    real_neo4j_backend.ensure_schema(target_version=2)  # second call is a no-op
    assert real_neo4j_backend.info().schema_version == 2
