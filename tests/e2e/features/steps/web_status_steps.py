"""Step definitions for web_status.feature.

Drives the Status surface via Playwright against a real TCP guru-server
instance started by the @web feature bootstrap in environment.py.

Graph state is emulated in-process by injecting a custom SyncService
into app.state so that drift, reconcile, and graph-disabled scenarios
can be tested without a real Neo4j or guru-graph daemon.
"""

from __future__ import annotations

from behave import given, then, when

from guru_server.sync import SyncService

# ---------------------------------------------------------------------------
# In-process fakes for SyncService
# ---------------------------------------------------------------------------


class _FakeLanceAdapterForWeb:
    """Reads document IDs directly from the running server's VectorStore.

    VectorStore.list_documents() returns dicts with a ``file_path`` key.
    VectorStore.get_document() also returns ``file_path`` (not ``path``).
    We normalise here so SyncService gets the ``(id, title, path)`` triple
    it expects.
    """

    def __init__(self, store) -> None:
        self._store = store

    def list_document_ids(self) -> list[str]:
        return [
            row.get("file_path") or row.get("path", "") for row in self._store.list_documents()
        ]

    def get_document(self, doc_id: str) -> dict:
        row = self._store.get_document(doc_id)
        if row is None:
            raise KeyError(doc_id)
        file_path = row.get("file_path") or row.get("path", doc_id)
        fm = row.get("frontmatter") or {}
        title = fm.get("title") if isinstance(fm, dict) else None
        title = title or file_path.split("/")[-1]
        return {"id": file_path, "title": title, "path": file_path}


class _FakeGraphBackendForWeb:
    """In-process fake graph backend for web status BDD scenarios.

    Stores document node IDs in memory; supports prune() to simulate
    graph store wipe. The reconcile path upserts/deletes nodes here.
    """

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._nodes: dict[str, dict] = {}

    def is_enabled(self) -> bool:
        return self._enabled

    def list_document_node_ids(self, kb: str) -> list[str]:
        return list(self._nodes)

    def upsert_document_node(self, kb: str, document: dict) -> None:
        self._nodes[document["id"]] = dict(document)

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        self._nodes.pop(doc_id, None)

    def prune(self) -> None:
        """Clear all document nodes — simulates graph store wipe."""
        self._nodes.clear()


def _inject_sync_service(context, *, graph_enabled: bool) -> _FakeGraphBackendForWeb:
    """Replace app.state.sync with a fresh SyncService backed by fakes.

    Returns the _FakeGraphBackendForWeb so callers can prune or inspect it.
    """
    app = context.app
    store = app.state.store  # VectorStore instance wired in create_app

    lance_adapter = _FakeLanceAdapterForWeb(store=store)
    graph_backend = _FakeGraphBackendForWeb(enabled=graph_enabled)

    kb = app.state.project_name
    sync = SyncService(kb=kb, lance=lance_adapter, graph=graph_backend)

    # If graph is enabled, pre-seed the graph backend with all currently
    # indexed documents so the initial drift is 0 (everything in sync).
    if graph_enabled:
        for doc_id in lance_adapter.list_document_ids():
            doc = lance_adapter.get_document(doc_id)
            graph_backend.upsert_document_node(kb, doc)

    app.state.sync = sync
    app.state.graph_enabled = graph_enabled

    return graph_backend


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("the graph daemon is enabled for status")
def step_graph_enabled_for_status(context):
    """Enable graph and install a fake SyncService for status BDD scenarios."""
    context._web_status_graph = _inject_sync_service(context, graph_enabled=True)


@given("the graph daemon is disabled for status")
def step_graph_disabled_for_status(context):
    """Disable graph and install a fake SyncService for status BDD scenarios."""
    context._web_status_graph = _inject_sync_service(context, graph_enabled=False)


@given("the graph store is pruned for status")
def step_graph_pruned_for_status(context):
    """Wipe all graph nodes to create drift in the status surface."""
    graph_backend = getattr(context, "_web_status_graph", None)
    if graph_backend is None:
        raise RuntimeError(
            "context._web_status_graph not set — run 'the graph daemon is enabled for status' first"
        )
    graph_backend.prune()


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("I open the Status surface")
def step_open_status(context):
    context.page.goto(f"{context.server_url}/#/status")
    context.page.wait_for_load_state("networkidle")


@when('I click "Reconcile now"')
def step_click_reconcile(context):
    context.page.get_by_role("button", name="Reconcile now").click()


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then('I see the drift value "{value}"')
def step_see_drift(context, value):
    """Assert the drift card shows the expected numeric value.

    The drift Card renders:
      <div class="text-xs ...">drift</div>
      <div class="text-3xl ...">N</div>

    We wait until any element with that exact text appears on the page,
    giving the React query cache time to update after a reconcile.
    """
    context.page.wait_for_function(
        f'Array.from(document.querySelectorAll("*")).some(el => el.textContent.trim() === "{value}")',
        timeout=8000,
    )
    assert context.page.get_by_text(value, exact=True).count() > 0, (
        f"Expected drift value '{value}' to be visible on the page"
    )


@then('the "Reconcile now" button is disabled')
def step_reconcile_disabled(context):
    btn = context.page.get_by_role("button", name="Reconcile now")
    btn.wait_for(state="attached", timeout=8000)
    assert btn.is_disabled(), "Expected 'Reconcile now' button to be disabled"
