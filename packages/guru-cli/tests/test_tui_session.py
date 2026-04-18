from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.session import GuruSession
from guru_core.types import SearchResultOut, StatusResponse


@pytest.mark.asyncio
async def test_session_normalizes_status_snapshot():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    status_payload = {
        "server_running": True,
        "document_count": 5,
        "chunk_count": 42,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "graph_enabled": True,
        "graph_reachable": False,
    }
    parsed_status = StatusResponse.model_validate(status_payload)
    validate_calls = []

    def fake_validate(payload):
        validate_calls.append(payload)
        return parsed_status

    guru_client.status.return_value = status_payload
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(StatusResponse, "model_validate", staticmethod(fake_validate))
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)

    snapshot = await session.load_status()
    monkeypatch.undo()

    assert guru_client.status.await_count == 1
    assert validate_calls == [status_payload]
    assert snapshot.server_running is True
    assert snapshot.document_count == 5
    assert snapshot.chunk_count == 42
    assert snapshot.graph_enabled is True
    assert snapshot.graph_reachable is False
    assert not hasattr(snapshot, "current_job")


@pytest.mark.asyncio
async def test_session_normalizes_search_hits():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    search_payload = [
        {
            "file_path": "pkg/services/user.py",
            "header_breadcrumb": "UserService",
            "content": "class UserService:",
            "score": 0.98,
            "labels": ["code"],
            "chunk_level": 1,
            "artifact_qualname": "polyglot::pkg.services.user.UserService",
        }
    ]
    parsed_hit = SimpleNamespace(
        file_path="pkg/services/user.py",
        header_breadcrumb="UserService",
        content="class UserService:",
        score=0.98,
        labels=["code"],
        artifact_qualname="typed::pkg.services.user.UserService",
    )
    validate_calls = []

    def fake_validate(payload):
        validate_calls.append(payload)
        return parsed_hit

    guru_client.search.return_value = search_payload
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SearchResultOut, "model_validate", staticmethod(fake_validate))
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)

    hits = await session.run_search("UserService")
    monkeypatch.undo()

    assert guru_client.search.await_count == 1
    assert validate_calls == [search_payload[0]]
    assert hits[0].title == "UserService"
    assert hits[0].artifact_qualname == "typed::pkg.services.user.UserService"
