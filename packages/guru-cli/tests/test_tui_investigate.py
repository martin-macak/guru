from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession


@pytest.mark.asyncio
async def test_investigate_mode_shows_search_hits():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.search.return_value = [
        {
            "file_path": "docs/auth.md",
            "header_breadcrumb": "Authentication",
            "content": "OAuth authentication flow",
            "score": 0.91,
            "labels": ["documentation"],
            "chunk_level": 1,
        },
        {
            "file_path": "docs/oauth.md",
            "header_breadcrumb": "OAuth Internals",
            "content": "OAuth internal details",
            "score": 0.52,
            "labels": ["reference"],
            "chunk_level": 1,
        },
    ]
    guru_client.list_documents.return_value = [{"file_path": "docs/auth.md", "chunk_count": 3}]
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("/")
        await pilot.press("O", "A", "u", "t", "h", "enter")
        results = app.query_one("#results")
        assert results.renderable.plain == "Authentication"


@pytest.mark.asyncio
async def test_toggle_tree_reveals_knowledge_tree():
    session = GuruSession(guru_client=AsyncMock(), graph_client=AsyncMock())
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+b")
        tree = app.query_one("#knowledge-tree")
        assert tree.display is True
