"""Step definitions for sync_invariant.feature.

Uses pure in-process fakes (no real Neo4j, no live server) — every scenario
runs in the default CI suite. The harness is assembled fresh in each
Background / Scenario so scenarios are fully isolated.

SyncService's I/O methods are async. behave steps are sync, so we drive
each async call through ``asyncio.run``. The in-process `_FakeGraphBackend`
mirrors the real async contract: ``is_enabled`` sync, CRUD methods async.
"""

from __future__ import annotations

import asyncio

from behave import given, then, when

from guru_core.graph_types import SyncStatus
from guru_server.startup import run_startup_reconcile
from guru_server.sync import SyncService

# ---------------------------------------------------------------------------
# In-process fakes (same pattern as packages/guru-server/tests/conftest.py)
# ---------------------------------------------------------------------------


class _FakeLanceStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def list_document_ids(self) -> list[str]:
        return list(self._docs)

    def get_document(self, doc_id: str) -> dict:
        return self._docs.get(doc_id, {"id": doc_id, "title": doc_id, "path": doc_id})

    def add(self, doc_id: str) -> None:
        self._docs[doc_id] = {"id": doc_id, "title": doc_id, "path": doc_id}

    def remove(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)


class _FakeGraphBackend:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._nodes: dict[str, dict] = {}

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    async def list_document_node_ids(self, kb: str) -> list[str]:
        return list(self._nodes)

    async def upsert_document_node(self, kb: str, document: dict) -> None:
        self._nodes[document["id"]] = dict(document)

    async def delete_document_node(self, kb: str, doc_id: str) -> None:
        self._nodes.pop(doc_id, None)

    # Sync helpers used directly from step defs:
    def list_document_node_ids_sync(self) -> list[str]:
        return list(self._nodes)

    def prune(self) -> None:
        """Clear all document nodes (simulates graph store wipe)."""
        self._nodes.clear()


# ---------------------------------------------------------------------------
# Harness wiring
# ---------------------------------------------------------------------------


def _build_harness(graph_enabled: bool = True):
    lance = _FakeLanceStore()
    graph = _FakeGraphBackend(enabled=graph_enabled)
    svc = SyncService(kb="local", lance=lance, graph=graph)
    return lance, graph, svc


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given("a fresh sync harness")
def step_fresh_harness(context):
    """Build a brand-new in-process SyncService with empty fake adapters."""
    context.lance, context.graph, context.sync = _build_harness(graph_enabled=False)


@given("the graph daemon is enabled")
def step_graph_enabled_given(context):
    """Enable graph for the current harness.

    This step is shared between the sync_invariant feature (in-process
    SyncService fakes) and the web_graph feature (injects a mock
    graph_client into the running server). Dispatch based on which
    context attributes the active scenario provides.
    """
    app = getattr(context, "app", None)
    if app is not None:
        # Web scenario: delegate to the web_graph_steps helper so we keep
        # the mock construction in one place.
        from tests.e2e.features.steps.web_graph_steps import (
            _enable_graph_for_web_scenario,
        )

        _enable_graph_for_web_scenario(context)
        return
    # Sync-invariant scenario: flip the in-process fake.
    context.graph.set_enabled(True)


@given("the graph daemon is disabled")
def step_graph_disabled_given(context):
    """Disable graph for the current harness (web or in-process)."""
    app = getattr(context, "app", None)
    if app is not None:
        app.state.graph_client = None
        app.state.graph_enabled = False
        return
    context.graph.set_enabled(False)


@given('I ingest document "{name}"')
def step_given_ingest(context, name):
    """Seed a document into LanceDB and mirror it via SyncService.upsert_one."""
    context.lance.add(name)
    asyncio.run(context.sync.upsert_one({"id": name, "title": name, "path": name}))


@given("the graph store is pruned")
def step_given_prune(context):
    context.graph.prune()


@given('documents "{names}" exist in LanceDB')
def step_given_ingest_many(context, names):
    """Seed multiple documents into LanceDB only (not mirrored to graph)."""
    for name in [n.strip() for n in names.split(",")]:
        context.lance.add(name)


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when('I ingest document "{name}"')
def step_when_ingest(context, name):
    context.lance.add(name)
    asyncio.run(context.sync.upsert_one({"id": name, "title": name, "path": name}))


@when('I delete document "{name}"')
def step_when_delete(context, name):
    context.lance.remove(name)
    asyncio.run(context.sync.delete_one(name))


@when("I enable the graph daemon")
def step_when_enable_graph(context):
    context.graph.set_enabled(True)


@when("the graph store is pruned")
def step_when_prune(context):
    context.graph.prune()


@when("I trigger a reconcile")
def step_when_reconcile(context):
    asyncio.run(context.sync.reconcile())


@when("the server restarts")
def step_when_restart(context):
    """Simulate server startup: run_startup_reconcile against the current state."""
    asyncio.run(run_startup_reconcile(context.sync))


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


@then('the graph has a document node "{name}"')
def step_then_graph_has(context, name):
    ids = context.graph.list_document_node_ids_sync()
    assert name in ids, f"expected graph to contain document node '{name}', found: {ids}"


@then('the graph has no document node "{name}"')
def step_then_graph_has_not(context, name):
    ids = context.graph.list_document_node_ids_sync()
    assert name not in ids, (
        f"expected graph NOT to contain document node '{name}', but it does: {ids}"
    )


@then("sync drift is {n:d}")
def step_then_drift(context, n):
    status: SyncStatus = asyncio.run(context.sync.status())
    assert status.drift == n, (
        f"expected drift={n}, got drift={status.drift} "
        f"(lancedb={status.lancedb_count}, graph={status.graph_count}, "
        f"enabled={status.graph_enabled})"
    )
