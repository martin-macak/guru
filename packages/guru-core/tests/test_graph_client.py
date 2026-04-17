from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable


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
