"""Unit tests for GraphClient read methods: describe_artifact, neighbors, find_artifacts, graph_query."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    ArtifactFindQuery,
    ArtifactNeighborsResult,
    ArtifactNode,
)


def _client() -> GraphClient:
    return GraphClient(socket_path="/tmp/x.sock", auto_start=False)


def _artifact_dict(**overrides) -> dict:
    base = {
        "id": "polyglot::docs/guide.md",
        "label": "Document",
        "properties": {"kb_name": "polyglot"},
        "annotations": [],
        "links_out": [],
        "links_in": [],
    }
    base.update(overrides)
    return base


def _neighbors_dict(**overrides) -> dict:
    base = {
        "node_id": "polyglot::a",
        "nodes": [],
        "edges": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# describe_artifact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_describe_artifact_returns_node_on_200():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: _artifact_dict()
    with patch.object(client, "_request", return_value=resp):
        result = await client.describe_artifact(node_id="polyglot::docs/guide.md")
    assert isinstance(result, ArtifactNode)
    assert result.id == "polyglot::docs/guide.md"
    assert result.label == "Document"


@pytest.mark.asyncio
async def test_describe_artifact_returns_none_on_404():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 404
    with patch.object(client, "_request", return_value=resp):
        result = await client.describe_artifact(node_id="polyglot::missing")
    assert result is None


@pytest.mark.asyncio
async def test_describe_artifact_raises_on_unexpected_status():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 201
    with patch.object(client, "_request", return_value=resp), pytest.raises(GraphUnavailable):
        await client.describe_artifact(node_id="polyglot::docs/guide.md")


@pytest.mark.asyncio
async def test_describe_artifact_url_encodes_node_id():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: _artifact_dict(id="polyglot::pkg/x.py::Foo")
    with patch.object(client, "_request", return_value=resp) as r:
        await client.describe_artifact(node_id="polyglot::pkg/x.py::Foo")
    path = r.call_args.args[1]
    # / and : must be percent-encoded (safe='')
    assert "polyglot%3A%3Apkg%2Fx.py%3A%3AFoo" in path


# ---------------------------------------------------------------------------
# neighbors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_neighbors_default_query_string():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: _neighbors_dict()
    with patch.object(client, "_request", return_value=resp) as r:
        await client.neighbors(node_id="polyglot::a")
    path = r.call_args.args[1]
    assert "?direction=both&rel_type=both&depth=1&limit=50" in path


@pytest.mark.asyncio
async def test_neighbors_with_kind_appends_filter():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: _neighbors_dict()
    with patch.object(client, "_request", return_value=resp) as r:
        await client.neighbors(node_id="polyglot::a", kind="imports")
    path = r.call_args.args[1]
    assert "&kind=imports" in path


@pytest.mark.asyncio
async def test_neighbors_returns_result_on_200():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: _neighbors_dict(node_id="polyglot::a", nodes=[], edges=[])
    with patch.object(client, "_request", return_value=resp):
        result = await client.neighbors(node_id="polyglot::a")
    assert isinstance(result, ArtifactNeighborsResult)
    assert result.node_id == "polyglot::a"


@pytest.mark.asyncio
async def test_neighbors_raises_on_unexpected_status():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 404
    with patch.object(client, "_request", return_value=resp), pytest.raises(GraphUnavailable):
        await client.neighbors(node_id="polyglot::missing")


# ---------------------------------------------------------------------------
# find_artifacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_artifacts_posts_query_excluding_none():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: []
    with patch.object(client, "_request", return_value=resp) as r:
        await client.find_artifacts(ArtifactFindQuery(name="UserService"))
    body = r.call_args.kwargs["json"]
    assert body == {"name": "UserService", "limit": 50}


@pytest.mark.asyncio
async def test_find_artifacts_returns_list_on_200():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: [_artifact_dict()]
    with patch.object(client, "_request", return_value=resp):
        results = await client.find_artifacts(ArtifactFindQuery(label="Document"))
    assert len(results) == 1
    assert isinstance(results[0], ArtifactNode)


@pytest.mark.asyncio
async def test_find_artifacts_returns_empty_list_on_no_match():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: []
    with patch.object(client, "_request", return_value=resp):
        results = await client.find_artifacts(ArtifactFindQuery(name="NoSuchThing"))
    assert results == []


@pytest.mark.asyncio
async def test_find_artifacts_raises_on_unexpected_status():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 422
    with patch.object(client, "_request", return_value=resp), pytest.raises(GraphUnavailable):
        await client.find_artifacts(ArtifactFindQuery(name="x"))


# ---------------------------------------------------------------------------
# graph_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_query_forces_read_only_true():
    client = _client()
    with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
        await client.graph_query(cypher="MATCH (n) RETURN n", params={"x": 1})
    assert mock_query.call_args.kwargs == {
        "cypher": "MATCH (n) RETURN n",
        "params": {"x": 1},
        "read_only": True,
    }


@pytest.mark.asyncio
async def test_graph_query_passes_params_through():
    client = _client()
    with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
        await client.graph_query(
            cypher="MATCH (n:KB {name: $name}) RETURN n", params={"name": "polyglot"}
        )
    assert mock_query.call_args.kwargs["params"] == {"name": "polyglot"}
    assert mock_query.call_args.kwargs["read_only"] is True
