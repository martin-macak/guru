from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.controllers.graph import GraphController
from guru_cli.tui.session import FakeArtifactGraphGateway, GuruSession
from guru_cli.tui.view_models import GraphNodeVM
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import ArtifactNeighborsResult, ArtifactNode


@pytest.mark.asyncio
async def test_fake_artifact_gateway_returns_bounded_neighborhood():
    gateway = FakeArtifactGraphGateway()
    gateway.seed(
        nodes=[
            GraphNodeVM(node_id="artifact::root", label="Root", kind="artifact"),
            GraphNodeVM(node_id="artifact::child", label="Child", kind="artifact"),
            GraphNodeVM(node_id="artifact::leaf", label="Leaf", kind="artifact"),
        ],
        edges=[
            {"from_id": "artifact::root", "to_id": "artifact::child", "rel_type": "contains"},
            {"from_id": "artifact::child", "to_id": "artifact::leaf", "rel_type": "contains"},
        ],
    )
    session = GuruSession(
        guru_client=AsyncMock(), graph_client=AsyncMock(), artifact_gateway=gateway
    )

    nodes, edges = await session.load_graph_neighbors("artifact::root", depth=1)

    assert [node.node_id for node in nodes] == ["artifact::root", "artifact::child"]
    assert [(edge.from_id, edge.to_id) for edge in edges] == [
        ("artifact::root", "artifact::child")
    ]


@pytest.mark.asyncio
async def test_graph_controller_delegates_to_session_gateway():
    gateway = FakeArtifactGraphGateway()
    gateway.seed(
        nodes=[{"node_id": "artifact::root", "label": "Root"}],
        edges=[],
    )
    session = GuruSession(
        guru_client=AsyncMock(), graph_client=AsyncMock(), artifact_gateway=gateway
    )
    controller = GraphController(session)

    nodes, edges = await controller.load_neighborhood("artifact::root", depth=2)

    assert [node.node_id for node in nodes] == ["artifact::root"]
    assert edges == []


@pytest.mark.asyncio
async def test_fake_artifact_gateway_deduplicates_edges_in_cyclic_neighborhoods():
    gateway = FakeArtifactGraphGateway()
    gateway.seed(
        nodes=[
            {"node_id": "artifact::root", "label": "Root"},
            {"node_id": "artifact::child", "label": "Child"},
            {"node_id": "artifact::leaf", "label": "Leaf"},
        ],
        edges=[
            {"from_id": "artifact::root", "to_id": "artifact::child", "rel_type": "contains"},
            {"from_id": "artifact::child", "to_id": "artifact::leaf", "rel_type": "contains"},
            {"from_id": "artifact::leaf", "to_id": "artifact::root", "rel_type": "references"},
        ],
    )
    session = GuruSession(
        guru_client=AsyncMock(), graph_client=AsyncMock(), artifact_gateway=gateway
    )

    nodes, edges = await session.load_graph_neighbors("artifact::root", depth=2)

    assert [node.node_id for node in nodes] == [
        "artifact::root",
        "artifact::child",
        "artifact::leaf",
    ]
    assert [(edge.from_id, edge.to_id, edge.rel_type) for edge in edges] == [
        ("artifact::root", "artifact::child", "contains"),
        ("artifact::leaf", "artifact::root", "references"),
        ("artifact::child", "artifact::leaf", "contains"),
    ]


@pytest.mark.asyncio
async def test_graph_mode_renders_selection_centered_neighborhood():
    gateway = FakeArtifactGraphGateway()
    gateway.seed(
        nodes=[
            {"node_id": "artifact::root", "label": "Root"},
            {"node_id": "artifact::child", "label": "Child"},
        ],
        edges=[{"from_id": "artifact::root", "to_id": "artifact::child", "rel_type": "contains"}],
    )
    session = GuruSession(
        guru_client=AsyncMock(), graph_client=AsyncMock(), artifact_gateway=gateway
    )
    app = WorkbenchApp(session=session)
    app._state = app._state.with_node("artifact::root")

    async with app.run_test() as pilot:
        await pilot.press("2")
        viewport = app.query_one("#graph-viewport")
        assert "Graph nodes:" in viewport.renderable.plain
        assert "Root (artifact::root)" in viewport.renderable.plain
        assert "Child (artifact::child)" in viewport.renderable.plain
        assert "artifact::root -> artifact::child [contains]" in viewport.renderable.plain


@pytest.mark.asyncio
async def test_graph_mode_handles_missing_selection_without_gateway_calls():
    session = GuruSession(guru_client=AsyncMock(), graph_client=AsyncMock(), artifact_gateway=None)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("2")
        viewport = app.query_one("#graph-viewport")
        assert viewport.renderable.plain == "Graph: no selection"


@pytest.mark.asyncio
async def test_graph_session_uses_real_graph_client_when_no_fake_gateway_is_configured():
    graph_client = AsyncMock()
    graph_client.neighbors.return_value = ArtifactNeighborsResult(
        node_id="alpha::docs/guide.md",
        nodes=[
            ArtifactNode(id="alpha::docs/guide.md", label="Document", properties={}),
            ArtifactNode(id="alpha::docs/guide.md::Intro", label="MarkdownSection", properties={}),
        ],
        edges=[
            {
                "from_id": "alpha::docs/guide.md",
                "to_id": "alpha::docs/guide.md::Intro",
                "rel_type": "CONTAINS",
            }
        ],
    )
    session = GuruSession(
        guru_client=AsyncMock(), graph_client=graph_client, artifact_gateway=None
    )

    nodes, edges = await session.load_graph_neighbors("alpha::docs/guide.md", depth=2)

    assert [node.node_id for node in nodes] == [
        "alpha::docs/guide.md",
        "alpha::docs/guide.md::Intro",
    ]
    assert [node.kind for node in nodes] == ["Document", "MarkdownSection"]
    assert [(edge.from_id, edge.to_id, edge.rel_type) for edge in edges] == [
        ("alpha::docs/guide.md", "alpha::docs/guide.md::Intro", "CONTAINS")
    ]
    graph_client.neighbors.assert_awaited_once_with(
        "alpha::docs/guide.md",
        depth=2,
    )


@pytest.mark.asyncio
async def test_graph_session_returns_empty_graph_when_real_graph_is_unavailable():
    graph_client = AsyncMock()
    graph_client.neighbors.side_effect = GraphUnavailable("daemon unreachable")
    session = GuruSession(
        guru_client=AsyncMock(), graph_client=graph_client, artifact_gateway=None
    )

    nodes, edges = await session.load_graph_neighbors("alpha::docs/guide.md", depth=1)

    assert nodes == []
    assert edges == []
