from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import QueryResult


@pytest.mark.asyncio
async def test_query_mode_runs_read_only_cypher():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    graph_client.query.return_value = QueryResult(columns=["n"], rows=[[1]], elapsed_ms=1.2)
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("3")
        editor = app.query_one("#query-input")
        editor.value = "RETURN 1 AS n"
        await pilot.press("ctrl+enter")
        results = app.query_one("#query-results")
        assert "n" in results.renderable.plain
        assert "1" in results.renderable.plain
    graph_client.query.assert_awaited_once()
    assert graph_client.query.await_args.kwargs["cypher"] == "RETURN 1 AS n"
    assert graph_client.query.await_args.kwargs["read_only"] is True


@pytest.mark.asyncio
async def test_query_mode_reports_graph_unavailable_without_graph_client():
    session = GuruSession(guru_client=AsyncMock(), graph_client=None)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("3")
        editor = app.query_one("#query-input")
        editor.value = "RETURN 1 AS n"
        await pilot.press("ctrl+enter")
        results = app.query_one("#query-results")
        assert "Graph unavailable" in results.renderable.plain


@pytest.mark.asyncio
async def test_query_mode_reports_graph_unavailable_when_graph_query_fails():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    graph_client.query.side_effect = GraphUnavailable("socket missing: /tmp/graph.sock")
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("3")
        editor = app.query_one("#query-input")
        editor.value = "RETURN 1 AS n"
        await pilot.press("ctrl+enter")
        results = app.query_one("#query-results")
        assert "Graph unavailable" in results.renderable.plain
        assert "/tmp/graph.sock" in results.renderable.plain
