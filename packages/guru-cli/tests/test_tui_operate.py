from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession


@pytest.mark.asyncio
async def test_operate_mode_renders_status_snapshot():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.status.return_value = {
        "server_running": True,
        "document_count": 7,
        "chunk_count": 55,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "graph_enabled": True,
        "graph_reachable": True,
    }
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("4")
        body = app.query_one("#operate-body")
        assert "documents: 7" in body.renderable.plain
        assert "graph: reachable" in body.renderable.plain


@pytest.mark.asyncio
async def test_operate_refresh_button_reloads_status_snapshot():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.status.side_effect = [
        {
            "server_running": True,
            "document_count": 7,
            "chunk_count": 55,
            "last_indexed": None,
            "ollama_available": True,
            "model_loaded": True,
            "current_job": None,
            "graph_enabled": True,
            "graph_reachable": True,
        },
        {
            "server_running": True,
            "document_count": 8,
            "chunk_count": 60,
            "last_indexed": None,
            "ollama_available": True,
            "model_loaded": True,
            "current_job": None,
            "graph_enabled": True,
            "graph_reachable": False,
        },
    ]
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.click("#operate-refresh")
        body = app.query_one("#operate-body")
        assert guru_client.status.await_count == 2
        assert "documents: 8" in body.renderable.plain
        assert "graph: unreachable" in body.renderable.plain


@pytest.mark.asyncio
async def test_operate_reindex_button_triggers_job_and_updates_status_message():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.status.return_value = {
        "server_running": True,
        "document_count": 7,
        "chunk_count": 55,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "graph_enabled": True,
        "graph_reachable": True,
    }
    guru_client.trigger_index.return_value = {
        "job_id": "job-123",
        "status": "queued",
        "message": "Indexing started",
    }
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.click("#operate-reindex")
        body = app.query_one("#operate-body")
        assert guru_client.trigger_index.await_count == 1
        assert "Indexing started [queued] (job job-123)" in body.renderable.plain


@pytest.mark.asyncio
async def test_operate_reindex_button_preserves_existing_job_message():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.status.return_value = {
        "server_running": True,
        "document_count": 7,
        "chunk_count": 55,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "graph_enabled": True,
        "graph_reachable": True,
    }
    guru_client.trigger_index.return_value = {
        "job_id": "job-999",
        "status": "running",
        "message": "Indexing already in progress",
    }
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.click("#operate-reindex")
        body = app.query_one("#operate-body")
        assert guru_client.trigger_index.await_count == 1
        assert "Indexing already in progress [running] (job job-999)" in body.renderable.plain
