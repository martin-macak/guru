from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_types import GraphNodePayload, ParseResultPayload


@pytest.mark.asyncio
async def test_submit_parse_result_posts_payload(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "x.sock"), auto_start=False)
    payload = ParseResultPayload(
        chunks_count=0,
        document=GraphNodePayload(node_id="kb::x", label="Document", properties={}),
        nodes=[],
        edges=[],
    )
    fake_response = AsyncMock()
    fake_response.status_code = 204
    with patch.object(client, "_request", AsyncMock(return_value=fake_response)) as mock_request:
        await client.submit_parse_result(kb_name="kb", payload=payload)

    mock_request.assert_awaited_once()
    method, path = mock_request.await_args.args[:2]
    assert method == "POST"
    assert path == "/ingest/parse-result?kb_name=kb"
    assert "json" in mock_request.await_args.kwargs


@pytest.mark.asyncio
async def test_delete_document_calls_delete(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "x.sock"), auto_start=False)
    fake_response = AsyncMock()
    fake_response.status_code = 204
    with patch.object(client, "_request", AsyncMock(return_value=fake_response)) as mock_request:
        await client.delete_document_in_graph(kb_name="kb", doc_id="kb::x.md")

    method, path = mock_request.await_args.args[:2]
    assert method == "DELETE"
    assert path == "/ingest/documents/kb%3A%3Ax.md?kb_name=kb"
