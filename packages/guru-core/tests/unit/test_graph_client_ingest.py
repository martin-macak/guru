"""Unit tests for GraphClient.submit_parse_result + delete_document_in_graph."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import GraphNodePayload, ParseResultPayload


def _client() -> GraphClient:
    return GraphClient(socket_path="/tmp/x.sock", auto_start=False)


def _payload() -> ParseResultPayload:
    return ParseResultPayload(
        chunks_count=0,
        document=GraphNodePayload(node_id="kb::x", label="Document", properties={}),
        nodes=[],
        edges=[],
    )


@pytest.mark.asyncio
async def test_submit_parse_result_posts_encoded_query_string():
    client = _client()
    fake_response = AsyncMock()
    fake_response.status_code = 204
    with patch.object(client, "_request", return_value=fake_response) as r:
        await client.submit_parse_result(kb_name="my kb", payload=_payload())

    assert r.called
    args, kwargs = r.call_args.args, r.call_args.kwargs
    assert args[0] == "POST"
    # kb_name should be URL-encoded (space → %20)
    assert args[1] == "/ingest/parse-result?kb_name=my%20kb"
    assert "json" in kwargs
    assert kwargs["json"]["document"]["node_id"] == "kb::x"


@pytest.mark.asyncio
async def test_submit_parse_result_raises_on_non_204():
    client = _client()
    fake_response = AsyncMock()
    fake_response.status_code = 200  # unexpected "success" — still an error
    with (
        patch.object(client, "_request", return_value=fake_response),
        pytest.raises(GraphUnavailable),
    ):
        await client.submit_parse_result(kb_name="kb", payload=_payload())


@pytest.mark.asyncio
async def test_delete_document_issues_percent_encoded_path():
    client = _client()
    fake_response = AsyncMock()
    fake_response.status_code = 204
    with patch.object(client, "_request", return_value=fake_response) as r:
        await client.delete_document_in_graph(kb_name="kb", doc_id="kb::docs/guide.md")

    args = r.call_args.args
    assert args[0] == "DELETE"
    # Every special character in doc_id must be percent-encoded (safe='')
    assert args[1] == "/ingest/documents/kb%3A%3Adocs%2Fguide.md?kb_name=kb"


@pytest.mark.asyncio
async def test_delete_document_raises_on_non_204():
    client = _client()
    fake_response = AsyncMock()
    fake_response.status_code = 404  # (our server doesn't return 404 here, but guard anyway)
    with (
        patch.object(client, "_request", return_value=fake_response),
        pytest.raises(GraphUnavailable),
    ):
        await client.delete_document_in_graph(kb_name="kb", doc_id="x")


@pytest.mark.asyncio
async def test_submit_parse_result_propagates_graph_unavailable_from_request():
    client = _client()

    async def _raise(*_a, **_kw):
        raise GraphUnavailable("simulated transport error")

    with (
        patch.object(client, "_request", side_effect=_raise),
        pytest.raises(GraphUnavailable, match="simulated"),
    ):
        await client.submit_parse_result(kb_name="kb", payload=_payload())
