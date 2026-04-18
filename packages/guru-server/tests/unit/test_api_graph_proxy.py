"""Unit tests for the /graph/* MCP-facing proxy routes.

Each route is exercised through a synthetic FastAPI app with a MagicMock
GraphClient on ``app.state.graph_client``. We assert:
  - graph_disabled fallback when client is None or raises GraphUnavailable
  - argument forwarding (path params, query params, body, headers)
  - status codes (200/201/404 mapping)
  - author header derivation precedence
  - read-only enforcement on /graph/query
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    AnnotationKind,
    AnnotationNode,
    ArtifactFindQuery,
    ArtifactLink,
    ArtifactLinkKind,
    ArtifactNeighborsResult,
    ArtifactNode,
    OrphanAnnotation,
    QueryResult,
)
from guru_server.api.graph import router

# --- helpers ---


def _build_app(client_mock):
    app = FastAPI()
    app.state.graph_client = client_mock
    app.include_router(router)
    return TestClient(app)


def _now() -> datetime:
    return datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)


def _artifact_node(node_id: str = "n1") -> ArtifactNode:
    return ArtifactNode(
        id=node_id,
        label="File",
        properties={"path": "src/foo.py"},
        annotations=[],
        links_out=[],
        links_in=[],
    )


def _annotation_node(ann_id: str = "a1", target_id: str = "n1") -> AnnotationNode:
    return AnnotationNode(
        id=ann_id,
        target_id=target_id,
        target_label="File",
        kind=AnnotationKind.NOTE,
        body="hello",
        tags=["t1"],
        author="user:test",
        created_at=_now(),
        updated_at=_now(),
        target_snapshot_json="{}",
    )


def _orphan_annotation(ann_id: str = "a1") -> OrphanAnnotation:
    return OrphanAnnotation(
        id=ann_id,
        kind=AnnotationKind.NOTE,
        body="orphaned",
        tags=[],
        author="user:test",
        created_at=_now(),
        updated_at=_now(),
        target_snapshot_json="{}",
    )


def _artifact_link(
    from_id: str = "n1",
    to_id: str = "n2",
    kind: ArtifactLinkKind = ArtifactLinkKind.IMPORTS,
) -> ArtifactLink:
    return ArtifactLink(
        from_id=from_id,
        to_id=to_id,
        kind=kind,
        created_at=_now(),
        author="user:test",
        metadata={},
    )


def _empty_neighbors(node_id: str = "n1") -> ArtifactNeighborsResult:
    return ArtifactNeighborsResult(node_id=node_id, nodes=[], edges=[])


def _make_client() -> MagicMock:
    """Build a MagicMock with the GraphClient spec and AsyncMock methods."""
    client = MagicMock(spec=GraphClient)
    client.describe_artifact = AsyncMock()
    client.neighbors = AsyncMock()
    client.find_artifacts = AsyncMock()
    client.create_annotation = AsyncMock()
    client.delete_annotation = AsyncMock()
    client.create_link = AsyncMock()
    client.delete_link = AsyncMock()
    client.list_orphans = AsyncMock()
    client.reattach_orphan = AsyncMock()
    client.graph_query = AsyncMock()
    return client


# --- graph_disabled (client is None) ---


def test_describe_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.get("/graph/describe/n1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_neighbors_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.get("/graph/neighbors/n1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_find_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.post("/graph/find", json={"name": "foo"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_annotations_create_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.post(
        "/graph/annotations",
        json={"node_id": "n1", "kind": "note", "body": "hi", "tags": []},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_query_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.post("/graph/query", json={"cypher": "RETURN 1", "params": {}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


# --- describe ---


def test_describe_forwards_node_id_and_returns_node():
    client = _make_client()
    client.describe_artifact.return_value = _artifact_node("module/foo.py")
    tc = _build_app(client)
    resp = tc.get("/graph/describe/module/foo.py")
    assert resp.status_code == 200
    assert resp.json()["id"] == "module/foo.py"
    client.describe_artifact.assert_awaited_once_with(node_id="module/foo.py")


def test_describe_returns_404_when_client_returns_none():
    client = _make_client()
    client.describe_artifact.return_value = None
    tc = _build_app(client)
    resp = tc.get("/graph/describe/missing")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_describe_swallows_graph_unavailable_to_disabled_body():
    client = _make_client()
    client.describe_artifact.side_effect = GraphUnavailable("down")
    tc = _build_app(client)
    resp = tc.get("/graph/describe/n1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


# --- neighbors ---


def test_neighbors_forwards_query_params():
    client = _make_client()
    client.neighbors.return_value = _empty_neighbors("n1")
    tc = _build_app(client)
    resp = tc.get(
        "/graph/neighbors/n1",
        params={
            "direction": "out",
            "rel_type": "RELATES",
            "kind": "imports",
            "depth": "2",
            "limit": "10",
        },
    )
    assert resp.status_code == 200
    client.neighbors.assert_awaited_once_with(
        node_id="n1",
        direction="out",
        rel_type="RELATES",
        kind="imports",
        depth=2,
        limit=10,
    )


def test_neighbors_swallows_graph_unavailable():
    client = _make_client()
    client.neighbors.side_effect = GraphUnavailable("down")
    tc = _build_app(client)
    resp = tc.get("/graph/neighbors/n1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


# --- find ---


def test_find_forwards_pydantic_body():
    client = _make_client()
    client.find_artifacts.return_value = [_artifact_node("hit1")]
    tc = _build_app(client)
    resp = tc.post("/graph/find", json={"name": "X", "limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["id"] == "hit1"
    # find_artifacts is called positionally with the parsed query.
    assert client.find_artifacts.await_count == 1
    call_args = client.find_artifacts.call_args
    arg = call_args.args[0] if call_args.args else call_args.kwargs.get("q")
    assert isinstance(arg, ArtifactFindQuery)
    assert arg.name == "X"
    assert arg.limit == 10


# --- create_annotation ---


def test_create_annotation_uses_x_guru_author_header():
    client = _make_client()
    client.create_annotation.return_value = _annotation_node()
    tc = _build_app(client)
    resp = tc.post(
        "/graph/annotations",
        json={"node_id": "n1", "kind": "note", "body": "hi", "tags": []},
        headers={"X-Guru-Author": "user:alice"},
    )
    assert resp.status_code == 201
    assert client.create_annotation.await_args.kwargs["author"] == "user:alice"


def test_create_annotation_falls_back_to_x_guru_mcp_client_header():
    client = _make_client()
    client.create_annotation.return_value = _annotation_node()
    tc = _build_app(client)
    resp = tc.post(
        "/graph/annotations",
        json={"node_id": "n1", "kind": "note", "body": "hi", "tags": []},
        headers={"x-guru-mcp-client": "claude-code"},
    )
    assert resp.status_code == 201
    assert client.create_annotation.await_args.kwargs["author"] == "agent:claude-code"


def test_create_annotation_defaults_to_user_unknown():
    client = _make_client()
    client.create_annotation.return_value = _annotation_node()
    tc = _build_app(client)
    resp = tc.post(
        "/graph/annotations",
        json={"node_id": "n1", "kind": "note", "body": "hi", "tags": []},
    )
    assert resp.status_code == 201
    assert client.create_annotation.await_args.kwargs["author"] == "user:unknown"


def test_create_annotation_returns_201():
    client = _make_client()
    client.create_annotation.return_value = _annotation_node("a1", "n1")
    tc = _build_app(client)
    resp = tc.post(
        "/graph/annotations",
        json={"node_id": "n1", "kind": "note", "body": "hi", "tags": []},
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "a1"


# --- delete_annotation ---


def test_delete_annotation_returns_404_when_client_returns_false():
    client = _make_client()
    client.delete_annotation.return_value = False
    tc = _build_app(client)
    resp = tc.delete("/graph/annotations/missing")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_delete_annotation_returns_deleted_true_on_success():
    client = _make_client()
    client.delete_annotation.return_value = True
    tc = _build_app(client)
    resp = tc.delete("/graph/annotations/a1")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    client.delete_annotation.assert_awaited_once_with(annotation_id="a1")


# --- create_link ---


def test_create_link_uses_x_guru_author_header():
    client = _make_client()
    client.create_link.return_value = _artifact_link()
    tc = _build_app(client)
    resp = tc.post(
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports", "metadata": {}},
        headers={"X-Guru-Author": "user:bob"},
    )
    assert resp.status_code == 201
    assert client.create_link.await_args.kwargs["author"] == "user:bob"


def test_create_link_returns_201():
    client = _make_client()
    client.create_link.return_value = _artifact_link()
    tc = _build_app(client)
    resp = tc.post(
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports", "metadata": {}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["from_id"] == "n1"
    assert body["to_id"] == "n2"
    assert body["kind"] == "imports"


# --- delete_link ---


def test_delete_link_forwards_body_to_client():
    client = _make_client()
    client.delete_link.return_value = True
    tc = _build_app(client)
    resp = tc.request(
        "DELETE",
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    client.delete_link.assert_awaited_once_with(
        from_id="n1", to_id="n2", kind=ArtifactLinkKind.IMPORTS
    )


def test_delete_link_returns_404_when_client_returns_false():
    client = _make_client()
    client.delete_link.return_value = False
    tc = _build_app(client)
    resp = tc.request(
        "DELETE",
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


# --- orphans ---


def test_orphans_forwards_limit():
    client = _make_client()
    client.list_orphans.return_value = [_orphan_annotation("a1")]
    tc = _build_app(client)
    resp = tc.get("/graph/orphans", params={"limit": "7"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    client.list_orphans.assert_awaited_once_with(limit=7)


def test_reattach_orphan_forwards_new_node_id():
    client = _make_client()
    client.reattach_orphan.return_value = _annotation_node("a1", "n2")
    tc = _build_app(client)
    resp = tc.post(
        "/graph/orphans/a1/reattach",
        json={"new_node_id": "n2"},
    )
    assert resp.status_code == 200
    assert resp.json()["target_id"] == "n2"
    client.reattach_orphan.assert_awaited_once_with(annotation_id="a1", new_node_id="n2")


# --- query (read-only enforced) ---


def test_query_forces_read_only_true_regardless_of_body():
    client = _make_client()
    client.graph_query.return_value = QueryResult(columns=["x"], rows=[[1]], elapsed_ms=0.5)
    tc = _build_app(client)
    resp = tc.post(
        "/graph/query",
        json={"cypher": "MATCH (n) RETURN n", "params": {}, "read_only": False},
    )
    assert resp.status_code == 200
    assert resp.json()["columns"] == ["x"]
    # The proxy must call graph_query (which itself enforces read_only=True
    # internally) - and it must NOT forward a read_only kwarg.
    assert client.graph_query.await_count == 1
    assert client.graph_query.call_args.kwargs == {
        "cypher": "MATCH (n) RETURN n",
        "params": {},
    }


# --- graph_disabled (client is None) for the remaining 5 routes ---


def test_delete_annotation_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.delete("/graph/annotations/a1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_create_link_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.post(
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports", "metadata": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_delete_link_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.request(
        "DELETE",
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_orphans_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.get("/graph/orphans")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_reattach_orphan_returns_graph_disabled_when_no_client():
    tc = _build_app(None)
    resp = tc.post("/graph/orphans/a1/reattach", json={"new_node_id": "n2"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


# --- GraphUnavailable swallow tests for the 8 remaining routes ---


def test_find_swallows_graph_unavailable():
    client = _make_client()
    client.find_artifacts.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.post("/graph/find", json={"name": "X"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_create_annotation_swallows_graph_unavailable():
    client = _make_client()
    client.create_annotation.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.post(
        "/graph/annotations",
        json={"node_id": "n1", "kind": "note", "body": "hi", "tags": []},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_delete_annotation_swallows_graph_unavailable():
    client = _make_client()
    client.delete_annotation.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.delete("/graph/annotations/a1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_create_link_swallows_graph_unavailable():
    client = _make_client()
    client.create_link.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.post(
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports", "metadata": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_delete_link_swallows_graph_unavailable():
    client = _make_client()
    client.delete_link.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.request(
        "DELETE",
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_list_orphans_swallows_graph_unavailable():
    client = _make_client()
    client.list_orphans.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.get("/graph/orphans")
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_reattach_orphan_swallows_graph_unavailable():
    client = _make_client()
    client.reattach_orphan.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.post("/graph/orphans/a1/reattach", json={"new_node_id": "n2"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


def test_query_swallows_graph_unavailable():
    client = _make_client()
    client.graph_query.side_effect = GraphUnavailable("simulated")
    tc = _build_app(client)
    resp = tc.post("/graph/query", json={"cypher": "RETURN 1", "params": {}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "graph_disabled"


# --- create_link author-header precedence ---


def test_create_link_falls_back_to_x_guru_mcp_client_header():
    client = _make_client()
    client.create_link.return_value = _artifact_link()
    tc = _build_app(client)
    resp = tc.post(
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports", "metadata": {}},
        headers={"x-guru-mcp-client": "claude-code"},
    )
    assert resp.status_code == 201
    assert client.create_link.call_args.kwargs["author"] == "agent:claude-code"


def test_create_link_defaults_to_user_unknown():
    client = _make_client()
    client.create_link.return_value = _artifact_link()
    tc = _build_app(client)
    resp = tc.post(
        "/graph/links",
        json={"from_id": "n1", "to_id": "n2", "kind": "imports", "metadata": {}},
    )
    assert resp.status_code == 201
    assert client.create_link.call_args.kwargs["author"] == "user:unknown"


# --- pytest discovery sanity (smoke) ---


@pytest.mark.parametrize(
    "path",
    [
        "/graph/describe/n1",
        "/graph/neighbors/n1",
        "/graph/orphans",
    ],
)
def test_get_routes_exist(path: str):
    tc = _build_app(None)
    resp = tc.get(path)
    assert resp.status_code == 200
