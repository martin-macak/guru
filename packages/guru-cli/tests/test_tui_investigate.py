from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession
from guru_cli.tui.state import WorkbenchMode


def _widget_text(widget) -> str:
    return str(widget.render())


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


@pytest.mark.asyncio
async def test_panel_visibility_labels_match_widget_display_with_symmetric_toggles():
    session = GuruSession(guru_client=AsyncMock(), graph_client=AsyncMock())
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        tree = app.query_one("#knowledge-tree")
        detail = app.query_one("#detail-panel")
        tree_label = app.query_one("#tree-label")
        detail_label = app.query_one("#detail-label")

        assert app._state.panels.tree_visible is False
        assert tree.display is False
        assert _widget_text(tree_label) == "Tree: hidden"

        assert app._state.panels.detail_visible is False
        assert detail.display is False
        assert _widget_text(detail_label) == "Detail: hidden"

        await pilot.press("ctrl+b", "ctrl+d")
        assert app._state.panels.tree_visible is True
        assert tree.display is True
        assert _widget_text(tree_label) == "Tree: visible"
        assert app._state.panels.detail_visible is True
        assert detail.display is True
        assert _widget_text(detail_label) == "Detail: visible"

        await pilot.press("ctrl+b", "ctrl+d")
        assert app._state.panels.tree_visible is False
        assert tree.display is False
        assert _widget_text(tree_label) == "Tree: hidden"
        assert app._state.panels.detail_visible is False
        assert detail.display is False
        assert _widget_text(detail_label) == "Detail: hidden"


@pytest.mark.asyncio
async def test_mode_binding_updates_workbench_state():
    session = GuruSession(guru_client=AsyncMock(), graph_client=AsyncMock())
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        mode_label = app.query_one("#mode-label")

        assert app._state.mode is WorkbenchMode.INVESTIGATE
        assert _widget_text(mode_label) == "Mode: Investigate"

        await pilot.press("2")

        assert app._state.mode is WorkbenchMode.GRAPH
        assert _widget_text(mode_label) == "Mode: Graph"
