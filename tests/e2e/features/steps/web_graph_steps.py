"""Step definitions for web_graph.feature.

Drives the Graph surface via Playwright against a real TCP guru-server
instance started by the @web feature bootstrap in environment.py.

The graph daemon is emulated in-process: the ``Given the graph daemon is
enabled`` step injects a mock graph_client into the already-running server's
app.state. This avoids the need for a real Neo4j or guru-graph process for
canvas-level BDD scenarios.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

from behave import given, then, when

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph_client_mock(*, kb_name: str = "local", docs: list[str] | None = None):
    """Build an AsyncMock for GraphClient with pre-seeded KB and document data.

    The mock wires:
    - get_kb(name)  →  KbNode(name=kb_name, ...)
    - neighbors(node_id, ...)  →  depends on node_id:
        * "kb:<kb_name>"  →  document neighbors
        * "doc:<x>"       →  document + linked-doc neighbors
    - graph_query(cypher=...)  →  single-doc result for MATCH queries
    """
    from datetime import UTC, datetime

    from guru_core.graph_types import (
        ArtifactNeighborsResult,
        ArtifactNode,
        GraphEdgePayload,
        KbNode,
        QueryResult,
    )

    doc_ids = [f"doc:{d}" for d in (docs or [])]
    now = datetime.now(UTC)
    kb_node = KbNode(
        name=kb_name,
        project_root=f"/tmp/{kb_name}",
        created_at=now,
        updated_at=now,
        tags=[],
    )

    # Track which docs are "linked" so neighbor traversal works in scenario 3.
    linked_pairs: list[tuple[str, str]] = []

    async def _get_kb(name: str):
        if name == kb_name:
            return kb_node
        return None

    async def _neighbors(
        node_id: str,
        direction="both",
        rel_type="both",
        kind=None,
        depth=1,
        limit=50,
    ) -> ArtifactNeighborsResult:
        kb_id = f"kb:{kb_name}"
        if node_id == kb_id:
            # Neighbors of the KB are its documents
            nodes = [
                ArtifactNode(
                    id=did,
                    label="Document",
                    properties={"kind": "document", "path": did.split(":", 1)[-1]},
                )
                for did in doc_ids
            ]
            edges = [
                GraphEdgePayload(
                    from_id=kb_id,
                    to_id=did,
                    rel_type="CONTAINS",
                    kind=None,
                    properties={},
                )
                for did in doc_ids
            ]
        elif node_id.startswith("doc:"):
            # Neighbors of a document: itself + any linked docs
            neighbor_nodes = [
                ArtifactNode(
                    id=other_id,
                    label="Document",
                    properties={"kind": "document", "path": other_id.split(":", 1)[-1]},
                )
                for (src, tgt) in linked_pairs
                for other_id in ([tgt] if src == node_id else [src] if tgt == node_id else [])
            ]
            nodes = neighbor_nodes
            edges = [
                GraphEdgePayload(
                    from_id=src,
                    to_id=tgt,
                    rel_type="RELATES",
                    kind="related_to",
                    properties={},
                )
                for (src, tgt) in linked_pairs
                if src == node_id or tgt == node_id
            ]
        else:
            nodes = []
            edges = []

        return ArtifactNeighborsResult(node_id=node_id, nodes=nodes, edges=edges)

    async def _graph_query(*, cypher: str, params=None) -> QueryResult:
        # Return a stub result that includes doc:a.md for MATCH queries.
        # The real Cypher execution path needs @real_neo4j; here we return
        # the first doc in the list so basic Cypher-projection scenarios pass.
        if doc_ids and cypher.strip().upper().startswith("MATCH"):
            first_doc = doc_ids[0]
            return QueryResult(
                columns=["d"],
                rows=[[{"id": first_doc, "label": "Document", "kind": "document"}]],
                elapsed_ms=1.0,
            )
        return QueryResult(columns=[], rows=[], elapsed_ms=0.0)

    mock = MagicMock()
    mock.get_kb = AsyncMock(side_effect=_get_kb)
    mock.neighbors = AsyncMock(side_effect=_neighbors)
    mock.graph_query = AsyncMock(side_effect=_graph_query)

    # Expose the linked_pairs list so the "link_documents" step can add to it.
    mock._linked_pairs = linked_pairs

    return mock


# ---------------------------------------------------------------------------
# Background / setup helpers
# ---------------------------------------------------------------------------
#
# The ``Given the graph daemon is enabled`` and ``Given the graph daemon is
# disabled`` step texts are shared with the sync_invariant feature
# (see sync_steps.py). The shared step dispatches here for @web scenarios
# via ``_enable_graph_for_web_scenario``.


def _enable_graph_for_web_scenario(context) -> None:
    """Inject a mock graph_client into the running web server.

    Called by the shared ``Given the graph daemon is enabled`` step in
    sync_steps.py when ``context.app`` is set (i.e. a @web scenario).
    """
    app = getattr(context, "app", None)
    if app is None:
        raise RuntimeError(
            "context.app is not set — ensure environment.py._start_web_server returns the app"
        )

    # KB name is the server's project name (see create_app in guru_server.app).
    kb_name = app.state.project_name

    # Guess which docs were created by the Background step.
    project_dir = getattr(context, "project_dir", None)
    doc_names: list[str] = []
    if project_dir is not None:
        docs_dir = project_dir / "docs"
        if docs_dir.exists():
            doc_names = sorted(p.name for p in docs_dir.glob("*.md"))

    mock_client = _make_graph_client_mock(kb_name=kb_name, docs=doc_names)

    app.state.graph_client = mock_client
    app.state.graph_enabled = True
    # Store the mock so later steps (e.g. link_documents) can update it.
    context._graph_mock = mock_client


@given('documents "{a}" and "{b}" are linked in the graph')
def step_link_docs(context, a, b):
    """Record a RELATES link between doc:a and doc:b in the mock graph_client.

    The mock's _linked_pairs list is checked by the _neighbors side_effect
    so clicking a document node returns its linked neighbor.
    """
    mock_client = getattr(context, "_graph_mock", None)
    if mock_client is None:
        raise RuntimeError(
            "Graph mock is not initialised — run 'the graph daemon is enabled' first"
        )
    from_id = f"doc:{a}"
    to_id = f"doc:{b}"
    mock_client._linked_pairs.append((from_id, to_id))


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


@when("I open the Graph surface")
def step_open_graph(context):
    context.page.goto(f"{context.server_url}/#/graph")
    context.page.wait_for_load_state("networkidle")
    # Brief wait for ReactFlow to mount and the canvas to settle.
    context.page.wait_for_timeout(500)


# ---------------------------------------------------------------------------
# Canvas assertions
# ---------------------------------------------------------------------------


@then('the canvas has node "{node_id}"')
def step_canvas_has_node(context, node_id):
    """ReactFlow renders nodes with data-id attributes on the outer wrapper."""
    locator = context.page.locator(f'[data-id="{node_id}"]')
    locator.wait_for(state="attached", timeout=15000)
    assert locator.count() > 0, f"Expected canvas node '{node_id}' to be present"


@then('the canvas does not have node "{node_id}"')
def step_canvas_missing_node(context, node_id):
    locator = context.page.locator(f'[data-id="{node_id}"]')
    assert locator.count() == 0, (
        f"Expected canvas node '{node_id}' to be absent, but it was present"
    )


@then("the canvas has {n:d} visible nodes")
def step_canvas_node_count(context, n):
    """Count ReactFlow node elements visible in the canvas."""
    # Wait for ReactFlow to finish rendering.
    time.sleep(0.3)
    count = context.page.locator(".react-flow__node").count()
    assert count == n, f"Expected {n} canvas nodes, got {count}"


# ---------------------------------------------------------------------------
# Canvas interactions
# ---------------------------------------------------------------------------


@when('I click the canvas node "{node_id}"')
def step_click_canvas_node(context, node_id):
    locator = context.page.locator(f'[data-id="{node_id}"]')
    locator.wait_for(state="attached", timeout=15000)
    locator.click()
    # Allow time for neighbor fetch + canvas re-render.
    context.page.wait_for_load_state("networkidle")
    context.page.wait_for_timeout(500)


# ---------------------------------------------------------------------------
# Path-to-root overlay
# ---------------------------------------------------------------------------


@then('a path-to-root overlay connects "{a}" to "{b}" to "{c}"')
def step_overlay(context, a, b, c):
    """Verify overlay edges in ReactFlow.

    GraphPage renders overlay edges with ids like "overlay:federation->kb:local".
    ReactFlow 11 renders each edge as
      <g class="react-flow__edge ..." data-testid="rf__edge-{id}">
    so we match on data-testid.
    """
    for pair in [(a, b), (b, c)]:
        edge_id = f"overlay:{pair[0]}->{pair[1]}"
        testid = f"rf__edge-{edge_id}"
        locator = context.page.locator(f'[data-testid="{testid}"]')
        assert locator.count() > 0, (
            f"Expected overlay edge '{edge_id}' in the canvas "
            f"(data-testid='{testid}') but it was absent"
        )


# ---------------------------------------------------------------------------
# Cypher query
# ---------------------------------------------------------------------------


@when('I run the Cypher query "{cypher}"')
def step_run_cypher(context, cypher):
    box = context.page.get_by_label("Cypher")
    box.fill(cypher)
    context.page.get_by_role("button", name="Run").click()
    context.page.wait_for_load_state("networkidle")
    context.page.wait_for_timeout(500)


@when('I click "Back to exploration"')
def step_back(context):
    context.page.get_by_role("button", name="Back to exploration").click()
    context.page.wait_for_timeout(300)


@then('the Cypher input shows the error "{text}"')
def step_error(context, text):
    """Verify the inline error message rendered by QueryInput."""
    # QueryInput renders errors in a <p role="alert"> below the input row.
    alert = context.page.get_by_role("alert")
    alert.wait_for(state="visible", timeout=10000)
    content = alert.inner_text()
    assert text in content, f"Expected error message to contain {text!r}, got: {content!r}"


# ---------------------------------------------------------------------------
# Generic message assertion
# ---------------------------------------------------------------------------


@then('I see the message "{msg}"')
def step_see_message(context, msg):
    """Assert that text is visible somewhere on the page."""
    element = context.page.get_by_text(msg)
    element.wait_for(state="visible", timeout=10000)
    assert element.is_visible(), f"Expected to see message {msg!r} but it was not visible"
