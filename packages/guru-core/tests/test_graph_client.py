from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import ArtifactFindQuery


@pytest.mark.asyncio
async def test_health_translates_connect_error_to_graph_unavailable(tmp_path):
    client = GraphClient(
        socket_path=str(tmp_path / "nope.sock"),
        auto_start=False,
    )
    with pytest.raises(GraphUnavailable):
        await client.health()


@pytest.mark.asyncio
async def test_426_response_raises_graph_unavailable(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "ok.sock"), auto_start=False)
    response = httpx.Response(
        status_code=426,
        json={"error": "protocol_upgrade_required", "supported": ["1.x"]},
    )
    fake_request = AsyncMock(return_value=response)
    with (
        pytest.raises(GraphUnavailable) as exc,
        patch.object(httpx.AsyncClient, "request", fake_request),
    ):
        await client.health()
    msg = str(exc.value).lower()
    assert "protocol" in msg or "426" in msg


@pytest.mark.asyncio
async def test_503_raises_graph_unavailable(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "ok.sock"), auto_start=False)
    response = httpx.Response(
        status_code=503,
        json={"error": "graph_unavailable", "detail": "neo4j down"},
    )
    fake_request = AsyncMock(return_value=response)
    with patch.object(httpx.AsyncClient, "request", fake_request), pytest.raises(GraphUnavailable):
        await client.health()


@pytest.mark.asyncio
async def test_auto_start_false_does_not_spawn(tmp_path):
    client = GraphClient(
        socket_path=str(tmp_path / "gone.sock"),
        auto_start=False,
    )
    with pytest.raises(GraphUnavailable):
        await client.health()


@pytest.mark.asyncio
async def test_describe_artifact_returns_none_for_404(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "ok.sock"), auto_start=False)
    response = httpx.Response(status_code=404, json={"detail": "missing"})
    with patch.object(GraphClient, "_request", AsyncMock(return_value=response)) as mock_request:
        node = await client.describe_artifact("alpha::missing")
    assert node is None
    mock_request.assert_awaited_once_with("GET", "/artifacts/alpha%3A%3Amissing")


@pytest.mark.asyncio
async def test_neighbors_builds_query_string_and_parses_payload(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "ok.sock"), auto_start=False)
    response = httpx.Response(
        status_code=200,
        json={
            "node_id": "alpha::pkg.Widget",
            "nodes": [
                {
                    "id": "alpha::pkg.Widget",
                    "label": "Class",
                    "properties": {"name": "Widget"},
                }
            ],
            "edges": [
                {
                    "from_id": "alpha::pkg",
                    "to_id": "alpha::pkg.Widget",
                    "rel_type": "CONTAINS",
                    "kind": None,
                }
            ],
        },
    )
    with patch.object(GraphClient, "_request", AsyncMock(return_value=response)) as mock_request:
        payload = await client.neighbors(
            "alpha::pkg.Widget",
            direction="both",
            rel_type="CONTAINS",
            kind="imports",
            depth=2,
            limit=10,
        )
    assert payload.node_id == "alpha::pkg.Widget"
    assert payload.edges[0].rel_type == "CONTAINS"
    mock_request.assert_awaited_once_with(
        "GET",
        "/artifacts/alpha%3A%3Apkg.Widget/neighbors"
        "?direction=both&rel_type=CONTAINS&depth=2&limit=10&kind=imports",
    )


@pytest.mark.asyncio
async def test_find_artifacts_posts_query_and_parses_results(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "ok.sock"), auto_start=False)
    response = httpx.Response(
        status_code=200,
        json=[
            {
                "id": "alpha::pkg.Widget",
                "label": "Class",
                "properties": {"name": "Widget"},
            }
        ],
    )
    query = ArtifactFindQuery(name="Widget", kb_name="alpha", limit=5)
    with patch.object(GraphClient, "_request", AsyncMock(return_value=response)) as mock_request:
        nodes = await client.find_artifacts(query)
    assert [node.id for node in nodes] == ["alpha::pkg.Widget"]
    mock_request.assert_awaited_once_with(
        "POST",
        "/artifacts/find",
        json={"name": "Widget", "kb_name": "alpha", "limit": 5},
    )
