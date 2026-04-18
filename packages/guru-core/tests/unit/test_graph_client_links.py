"""Unit tests for GraphClient artifact-link methods."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    ArtifactLink,
    ArtifactLinkCreate,
    ArtifactLinkKind,
)


def _client() -> GraphClient:
    return GraphClient(socket_path="/tmp/x.sock", auto_start=False)


def _link_dict(**overrides) -> dict:
    base = {
        "from_id": "kb::a",
        "to_id": "kb::b",
        "kind": "imports",
        "created_at": datetime.now(UTC).isoformat(),
        "author": "agent:test",
        "metadata": {},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_link_returns_artifact_link_and_sends_author_header():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 201
    resp.json = lambda: _link_dict()
    with patch.object(client, "_request", return_value=resp) as r:
        req = ArtifactLinkCreate(from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.IMPORTS)
        result = await client.create_link(req, author="agent:test")

    assert isinstance(result, ArtifactLink)
    assert result.from_id == "kb::a"
    assert result.to_id == "kb::b"
    assert r.call_args.args[0] == "POST"
    assert r.call_args.args[1] == "/relates"
    assert r.call_args.kwargs["headers"] == {"X-Guru-Author": "agent:test"}
    assert r.call_args.kwargs["json"] == req.model_dump(mode="json")


@pytest.mark.asyncio
async def test_create_link_raises_graph_unavailable_on_non_201():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 404
    resp.json = lambda: {"detail": "artifact not found"}
    with patch.object(client, "_request", return_value=resp):
        req = ArtifactLinkCreate(
            from_id="kb::missing", to_id="kb::b", kind=ArtifactLinkKind.IMPORTS
        )
        with pytest.raises(GraphUnavailable):
            await client.create_link(req, author="agent:test")


@pytest.mark.asyncio
async def test_create_link_raises_graph_unavailable_on_422():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 422
    resp.json = lambda: {"detail": "unprocessable entity"}
    with patch.object(client, "_request", return_value=resp):
        req = ArtifactLinkCreate(from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.IMPORTS)
        with pytest.raises(GraphUnavailable):
            await client.create_link(req, author="agent:test")


@pytest.mark.asyncio
async def test_delete_link_returns_true_on_204():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 204
    with patch.object(client, "_request", return_value=resp) as r:
        ok = await client.delete_link(
            from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.IMPORTS
        )
    assert ok is True
    assert r.call_args.args[0] == "DELETE"
    assert r.call_args.args[1] == "/relates"


@pytest.mark.asyncio
async def test_delete_link_returns_false_on_404():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 404
    with patch.object(client, "_request", return_value=resp):
        ok = await client.delete_link(
            from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.IMPORTS
        )
    assert ok is False


@pytest.mark.asyncio
async def test_delete_link_raises_graph_unavailable_on_unexpected_status():
    # Use 200 (passes through _request's 5xx guard) to exercise delete_link's own guard.
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    with patch.object(client, "_request", return_value=resp), pytest.raises(GraphUnavailable):
        await client.delete_link(from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.IMPORTS)


@pytest.mark.asyncio
async def test_delete_link_request_body_uses_enum_value():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 204
    with patch.object(client, "_request", return_value=resp) as r:
        await client.delete_link(from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.IMPORTS)
    assert r.call_args.kwargs["json"] == {
        "from_id": "kb::a",
        "to_id": "kb::b",
        "kind": "imports",
    }
