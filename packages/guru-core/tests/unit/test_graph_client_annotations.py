"""Unit tests for GraphClient annotation methods."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    AnnotationCreate,
    AnnotationKind,
    AnnotationNode,
    OrphanAnnotation,
)


def _client() -> GraphClient:
    return GraphClient(socket_path="/tmp/x.sock", auto_start=False)


def _annotation_dict(**overrides) -> dict:
    now = datetime.now(UTC).isoformat()
    base = {
        "id": "a-1",
        "target_id": "kb::UserService",
        "target_label": "Class",
        "kind": "gotcha",
        "body": "beware",
        "tags": [],
        "author": "agent:test",
        "created_at": now,
        "updated_at": now,
        "target_snapshot_json": '{"target_id":"kb::UserService"}',
    }
    base.update(overrides)
    return base


def _orphan_dict(**overrides) -> dict:
    now = datetime.now(UTC).isoformat()
    base = {
        "id": "a-1",
        "kind": "gotcha",
        "body": "beware",
        "tags": [],
        "author": "agent:test",
        "created_at": now,
        "updated_at": now,
        "target_snapshot_json": '{"target_id":"kb::gone"}',
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_create_annotation_returns_node_and_sends_author_header():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 201
    resp.json = lambda: _annotation_dict()
    with patch.object(client, "_request", return_value=resp) as r:
        req = AnnotationCreate(
            node_id="kb::UserService", kind=AnnotationKind.GOTCHA, body="beware"
        )
        result = await client.create_annotation(req, author="agent:test")

    assert isinstance(result, AnnotationNode)
    assert result.id == "a-1"
    assert r.call_args.kwargs["headers"] == {"X-Guru-Author": "agent:test"}
    assert r.call_args.args[0] == "POST"
    assert r.call_args.args[1] == "/annotations"


@pytest.mark.asyncio
async def test_create_annotation_raises_on_non_201():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 404  # target missing
    resp.json = lambda: {"detail": "target not found"}
    with patch.object(client, "_request", return_value=resp):
        req = AnnotationCreate(node_id="kb::missing", kind=AnnotationKind.NOTE, body="x")
        with pytest.raises(GraphUnavailable):
            await client.create_annotation(req, author="agent:test")


@pytest.mark.asyncio
async def test_delete_annotation_true_on_204():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 204
    with patch.object(client, "_request", return_value=resp) as r:
        ok = await client.delete_annotation(annotation_id="a-1")
    assert ok is True
    assert r.call_args.args[0] == "DELETE"
    assert r.call_args.args[1] == "/annotations/a-1"


@pytest.mark.asyncio
async def test_delete_annotation_false_on_404():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 404
    with patch.object(client, "_request", return_value=resp):
        ok = await client.delete_annotation(annotation_id="a-missing")
    assert ok is False


@pytest.mark.asyncio
async def test_list_orphans_parses_response():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: [_orphan_dict()]
    with patch.object(client, "_request", return_value=resp) as r:
        orphans = await client.list_orphans(limit=10)
    assert len(orphans) == 1
    assert isinstance(orphans[0], OrphanAnnotation)
    assert r.call_args.args[1] == "/annotations/orphans?limit=10"


@pytest.mark.asyncio
async def test_list_orphans_default_limit():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: []
    with patch.object(client, "_request", return_value=resp) as r:
        await client.list_orphans()
    assert r.call_args.args[1] == "/annotations/orphans?limit=50"


@pytest.mark.asyncio
async def test_reattach_orphan_posts_request_body_and_parses_response():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 200
    resp.json = lambda: _annotation_dict(target_id="kb::AccountService")
    with patch.object(client, "_request", return_value=resp) as r:
        result = await client.reattach_orphan(
            annotation_id="a-1", new_node_id="kb::AccountService"
        )
    assert isinstance(result, AnnotationNode)
    assert result.target_id == "kb::AccountService"
    assert r.call_args.args[0] == "POST"
    assert r.call_args.args[1] == "/annotations/a-1/reattach"
    assert r.call_args.kwargs["json"] == {"new_node_id": "kb::AccountService"}


@pytest.mark.asyncio
async def test_reattach_raises_on_non_200():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 404
    with patch.object(client, "_request", return_value=resp), pytest.raises(GraphUnavailable):
        await client.reattach_orphan(annotation_id="a-missing", new_node_id="kb::y")


@pytest.mark.asyncio
async def test_create_annotation_percent_encodes_nothing_special_in_id_free_path():
    """The create path has no id in the URL — just the body. Trivial test pinning
    that the path literally equals '/annotations'."""
    client = _client()
    resp = AsyncMock()
    resp.status_code = 201
    resp.json = lambda: _annotation_dict()
    with patch.object(client, "_request", return_value=resp) as r:
        await client.create_annotation(
            AnnotationCreate(node_id="kb::x", kind=AnnotationKind.NOTE, body="x"),
            author="agent:test",
        )
    assert r.call_args.args[1] == "/annotations"


@pytest.mark.asyncio
async def test_delete_annotation_url_encodes_id_with_specials():
    client = _client()
    resp = AsyncMock()
    resp.status_code = 204
    with patch.object(client, "_request", return_value=resp) as r:
        await client.delete_annotation(annotation_id="a/b c")
    # safe='' encodes / and space
    assert r.call_args.args[1] == "/annotations/a%2Fb%20c"
