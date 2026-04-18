from __future__ import annotations

import pytest

from guru_core.graph_types import (
    AnnotationKind,
    ArtifactLinkKind,
    GraphEdgePayload,
    GraphNodePayload,
    ParseResultPayload,
)


def test_artifact_link_kind_values():
    assert ArtifactLinkKind.IMPORTS == "imports"
    assert ArtifactLinkKind.INHERITS_FROM == "inherits_from"
    assert ArtifactLinkKind.IMPLEMENTS == "implements"
    assert ArtifactLinkKind.CALLS == "calls"
    assert ArtifactLinkKind.REFERENCES == "references"
    assert ArtifactLinkKind.DOCUMENTS == "documents"


def test_annotation_kind_values():
    assert set(AnnotationKind) == {
        AnnotationKind.SUMMARY,
        AnnotationKind.GOTCHA,
        AnnotationKind.CAVEAT,
        AnnotationKind.NOTE,
    }


def test_graph_node_payload_roundtrip():
    n = GraphNodePayload(node_id="kb::x", label="Document", properties={"a": 1})
    j = n.model_dump_json()
    assert GraphNodePayload.model_validate_json(j) == n


def test_parse_result_payload_contains_document():
    pr = ParseResultPayload(
        chunks_count=3,
        document=GraphNodePayload(node_id="kb::x", label="Document", properties={}),
        nodes=[],
        edges=[],
    )
    assert pr.document.label == "Document"


def test_graph_edge_relates_requires_kind():
    with pytest.raises(ValueError):
        GraphEdgePayload(from_id="a", to_id="b", rel_type="RELATES", kind=None)


def test_graph_edge_contains_forbids_kind():
    with pytest.raises(ValueError):
        GraphEdgePayload(from_id="a", to_id="b", rel_type="CONTAINS", kind="imports")
