"""Tests for the standardised POST /graph/query response shape.

Invariants:
- Response is always {nodes, edges}
- Each node has id, label, kind, kb (kb may be null)
- Each edge has source, target, kind
- The federation root node (id=="federation") is filtered out
- Cypher containing write keywords returns 400
- Deduplication by node id
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from guru_core.graph_types import QueryResult


def _make_query_result(rows: list[list]) -> QueryResult:
    """Build a QueryResult with synthetic rows (each cell is a dict)."""
    return QueryResult(columns=[], rows=rows, elapsed_ms=0.0)


@pytest.fixture
def test_app_with_graph_query(test_app_with_seed):
    """Extend the base fixture so graph_client.graph_query returns seeded data."""
    # Two document nodes, one edge, and the federation root (should be filtered)
    rows = [
        [
            {
                "id": "doc:readme.md",
                "label": "readme.md",
                "kind": "document",
                "kb": "test-kb",
            }
        ],
        [
            {
                "id": "doc:intro.md",
                "label": "intro.md",
                "kind": "document",
                "kb": "test-kb",
            }
        ],
        [
            {
                "id": "federation",
                "label": "Federation",
                "kind": "federation",
                "kb": None,
            }
        ],
        [
            {
                "source": "doc:readme.md",
                "target": "doc:intro.md",
                "kind": "references",
            }
        ],
    ]
    result = _make_query_result(rows)
    test_app_with_seed.state.graph_client.graph_query = AsyncMock(return_value=result)
    return test_app_with_seed


@pytest.fixture
def test_app_all_nodes(test_app_with_seed):
    """Fixture that returns the federation root plus a regular node."""
    rows = [
        [{"id": "doc:a.md", "label": "a.md", "kind": "document", "kb": "kb1"}],
        [{"id": "federation", "label": "Federation", "kind": "federation", "kb": None}],
    ]
    result = _make_query_result(rows)
    test_app_with_seed.state.graph_client.graph_query = AsyncMock(return_value=result)
    return test_app_with_seed


def test_graph_query_returns_nodes_and_edges(test_app_with_graph_query):
    client = TestClient(test_app_with_graph_query)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MATCH (d:Document) RETURN d LIMIT 5"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"nodes", "edges"}
    for node in body["nodes"]:
        assert {"id", "label", "kind", "kb"} <= set(node.keys())
    for edge in body["edges"]:
        assert {"source", "target", "kind"} <= set(edge.keys())


def test_graph_query_never_returns_federation_root(test_app_all_nodes):
    client = TestClient(test_app_all_nodes)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MATCH (n) RETURN n"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert all(n["id"] != "federation" for n in body["nodes"])


def test_graph_query_rejects_writes(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post(
        "/graph/query",
        json={"cypher": "CREATE (:Document {id: 'x.md'}) RETURN 1"},
    )
    assert resp.status_code == 400


def test_graph_query_rejects_merge(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MERGE (n:Document {id: 'x.md'}) RETURN n"},
    )
    assert resp.status_code == 400


def test_graph_query_rejects_delete(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MATCH (n) DELETE n"},
    )
    assert resp.status_code == 400


def test_graph_query_rejects_set(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MATCH (n {id: 'x'}) SET n.foo = 'bar' RETURN n"},
    )
    assert resp.status_code == 400


def test_graph_query_deduplicates_nodes(test_app_with_seed):
    """Duplicate node ids across rows should produce only one node."""
    rows = [
        [{"id": "doc:a.md", "label": "a.md", "kind": "document", "kb": "kb1"}],
        [{"id": "doc:a.md", "label": "a.md", "kind": "document", "kb": "kb1"}],
    ]
    result = _make_query_result(rows)
    test_app_with_seed.state.graph_client.graph_query = AsyncMock(return_value=result)

    client = TestClient(test_app_with_seed)
    resp = client.post("/graph/query", json={"cypher": "MATCH (n) RETURN n"})
    assert resp.status_code == 200
    body = resp.json()
    ids = [n["id"] for n in body["nodes"]]
    assert len(ids) == len(set(ids)), "duplicate node ids in response"


def test_graph_query_graph_disabled(test_app_graph_disabled):
    client = TestClient(test_app_graph_disabled)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MATCH (n) RETURN n"},
    )
    assert resp.status_code == 410
