from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    ArtifactFindQuery,
    ArtifactNeighborsResult,
    ArtifactNode,
    CypherQuery,
    GraphEdgePayload,
    GraphNodePayload,
    Health,
    KbLink,
    KbNode,
    KbUpsert,
    LinkKind,
    ParseResultPayload,
    QueryResult,
    VersionInfo,
)


def test_link_kind_enum_values():
    assert LinkKind.DEPENDS_ON.value == "depends_on"
    assert LinkKind.FORK_OF.value == "fork_of"
    assert LinkKind.REFERENCES.value == "references"
    assert LinkKind.RELATED_TO.value == "related_to"
    assert LinkKind.MIRRORS.value == "mirrors"
    assert {k.value for k in LinkKind} == {
        "depends_on",
        "fork_of",
        "references",
        "related_to",
        "mirrors",
    }


def test_link_kind_rejects_unknown_value():
    with pytest.raises(ValueError):
        LinkKind("sorta_related")


def test_kb_node_round_trip():
    now = datetime.now(UTC)
    node = KbNode(
        name="alpha",
        project_root="/tmp/alpha",
        created_at=now,
        updated_at=now,
        tags=["app"],
        metadata={"lang": "python"},
    )
    data = json.loads(node.model_dump_json())
    parsed = KbNode.model_validate(data)
    assert parsed == node


def test_kb_upsert_requires_name_and_project_root():
    with pytest.raises(ValidationError):
        KbUpsert(project_root="/tmp/x")
    with pytest.raises(ValidationError):
        KbUpsert(name="x")


def test_kb_link_uses_link_kind_enum():
    now = datetime.now(UTC)
    link = KbLink(
        from_kb="alpha",
        to_kb="beta",
        kind=LinkKind.DEPENDS_ON,
        created_at=now,
        metadata={},
    )
    assert link.kind is LinkKind.DEPENDS_ON
    parsed = KbLink.model_validate(json.loads(link.model_dump_json()))
    assert parsed.kind is LinkKind.DEPENDS_ON


def test_kb_link_rejects_unknown_kind():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        KbLink(from_kb="a", to_kb="b", kind="sorta", created_at=now)


def test_cypher_query_defaults():
    q = CypherQuery(cypher="MATCH (n) RETURN n")
    assert q.params == {}
    assert q.read_only is True


def test_health_status_literal():
    h = Health(
        status="healthy",
        graph_reachable=True,
        backend="neo4j",
        backend_version="5.24.0",
        schema_version=1,
    )
    assert h.status == "healthy"
    with pytest.raises(ValidationError):
        Health(
            status="fine",
            graph_reachable=True,
            backend="neo4j",
            backend_version="5.24.0",
            schema_version=1,
        )


def test_version_info_fields():
    v = VersionInfo(
        protocol_version="1.0.0", backend="neo4j", backend_version="5.24.0", schema_version=1
    )
    assert v.protocol_version == "1.0.0"


def test_query_result_shape():
    r = QueryResult(columns=["n"], rows=[["a"], ["b"]], elapsed_ms=1.2)
    assert r.columns == ["n"]
    assert r.rows == [["a"], ["b"]]


def test_artifact_node_round_trip():
    node = ArtifactNode(
        id="alpha::pkg.module.Widget",
        label="Class",
        properties={"name": "Widget", "kb_name": "alpha"},
    )
    parsed = ArtifactNode.model_validate_json(node.model_dump_json())
    assert parsed == node


def test_artifact_neighbors_result_shape():
    payload = ArtifactNeighborsResult(
        node_id="alpha::pkg.module.Widget",
        nodes=[
            ArtifactNode(
                id="alpha::pkg.module.Widget",
                label="Class",
                properties={"name": "Widget"},
            )
        ],
        edges=[
            {
                "from_id": "alpha::pkg.module",
                "to_id": "alpha::pkg.module.Widget",
                "rel_type": "CONTAINS",
                "kind": None,
            }
        ],
    )
    assert payload.nodes[0].id == "alpha::pkg.module.Widget"
    assert payload.edges[0].rel_type == "CONTAINS"


def test_artifact_find_query_defaults_and_validation():
    q = ArtifactFindQuery(name="Widget")
    assert q.limit == 50
    assert q.name == "Widget"
    with pytest.raises(ValidationError):
        ArtifactFindQuery(name="Widget", unexpected=True)


def test_parse_result_payload_round_trip():
    payload = ParseResultPayload(
        chunks_count=2,
        document=GraphNodePayload(
            node_id="alpha::docs/guide.md",
            label="Document",
            properties={"kb_name": "alpha"},
        ),
        nodes=[
            GraphNodePayload(
                node_id="alpha::docs/guide.md::Intro",
                label="MarkdownSection",
                properties={"breadcrumb": "Intro"},
            )
        ],
        edges=[
            GraphEdgePayload(
                from_id="alpha::docs/guide.md",
                to_id="alpha::docs/guide.md::Intro",
                rel_type="CONTAINS",
            )
        ],
    )
    parsed = ParseResultPayload.model_validate_json(payload.model_dump_json())
    assert parsed.document.node_id == "alpha::docs/guide.md"
    assert parsed.nodes[0].label == "MarkdownSection"
    assert parsed.edges[0].rel_type == "CONTAINS"


def test_graph_unavailable_is_runtime_error():
    err = GraphUnavailable("daemon unreachable")
    assert isinstance(err, RuntimeError)
    assert str(err) == "daemon unreachable"
