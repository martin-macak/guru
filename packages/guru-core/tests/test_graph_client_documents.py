from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from guru_core.graph_client import GraphClient


@pytest.mark.asyncio
async def test_list_document_nodes(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "x.sock"), auto_start=False)
    response = httpx.Response(
        200,
        json={"nodes": [{"id": "a.md", "kind": "document"}, {"id": "b.md", "kind": "document"}]},
    )
    with patch.object(GraphClient, "_request", AsyncMock(return_value=response)) as mock_request:
        nodes = await client.list_document_nodes("local")

    assert [n["id"] for n in nodes] == ["a.md", "b.md"]
    mock_request.assert_awaited_once_with("GET", "/graph/documents/local")


@pytest.mark.asyncio
async def test_upsert_document_node(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "x.sock"), auto_start=False)
    response = httpx.Response(204)
    with patch.object(GraphClient, "_request", AsyncMock(return_value=response)) as mock_request:
        await client.upsert_document_node("local", {"id": "a.md", "title": "A", "path": "a.md"})

    mock_request.assert_awaited_once_with(
        "POST",
        "/graph/documents/local",
        json={"id": "a.md", "title": "A", "path": "a.md"},
    )


@pytest.mark.asyncio
async def test_delete_document_node(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "x.sock"), auto_start=False)
    response = httpx.Response(204)
    with patch.object(GraphClient, "_request", AsyncMock(return_value=response)) as mock_request:
        await client.delete_document_node("local", "a.md")

    mock_request.assert_awaited_once_with(
        "DELETE",
        "/graph/documents/local/a.md",
    )
