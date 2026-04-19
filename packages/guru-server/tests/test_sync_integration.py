"""Integration tests for SyncService against the real GraphClient surface.

These tests use a fake (`AsyncGraphClientFake`) whose method signatures
MIRROR the actual `guru_core.graph_client.GraphClient` — i.e. the three
document-node methods are `async def` — so any regression where the
SyncService / GraphSyncAdapter invokes them without awaiting surfaces as
a real failure here, not as a silent `RuntimeWarning`.

The dev-server crashes we hit (`is_available` missing; `list_document_nodes`
coroutine never awaited) both came from fakes that drifted from the real
client's surface. These tests guard that boundary.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from guru_server.api import api_router
from guru_server.indexer import finalize_deleted_document, finalize_indexed_document
from guru_server.startup import run_startup_reconcile
from guru_server.sync import GraphSyncAdapter, LanceDocumentAdapter, SyncService


class AsyncGraphClientFake:
    """Mirrors the real `guru_core.graph_client.GraphClient` surface.

    Notably: document-node methods are ``async def``. Having them return
    coroutines — not plain values — is what makes this fake faithful to
    production. A bad adapter implementation that forgets ``await`` will
    either warn (RuntimeWarning), raise TypeError (iterating a coroutine),
    or leave the graph untouched — all visible here.

    Crucially there is NO ``is_available`` method: GraphClient doesn't have
    one either, and any code path that needs it is using the wrong
    abstraction.
    """

    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.upserts: list[tuple[str, str]] = []
        self.deletes: list[tuple[str, str]] = []

    async def list_document_nodes(self, kb: str) -> list[dict]:
        return [{"id": doc_id, "kind": "document"} for doc_id in sorted(self.documents)]

    async def upsert_document_node(self, kb: str, document: dict) -> None:
        self.documents[document["id"]] = dict(document)
        self.upserts.append((kb, document["id"]))

    async def delete_document_node(self, kb: str, doc_id: str) -> None:
        self.documents.pop(doc_id, None)
        self.deletes.append((kb, doc_id))


class LanceStoreFake:
    """Storage-shaped fake that the real LanceDocumentAdapter consumes."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def list_documents(self) -> list[dict]:
        return list(self._rows)

    def get_document(self, path: str) -> dict | None:
        for row in self._rows:
            if row["file_path"] == path:
                return row
        return None


def _make_sync(store_rows: list[dict[str, Any]], graph_enabled: bool = True) -> SyncService:
    client = AsyncGraphClientFake() if graph_enabled else None
    return SyncService(
        kb="local",
        lance=LanceDocumentAdapter(store=LanceStoreFake(store_rows)),
        graph=GraphSyncAdapter(client=client),
    )


# ---------- Production-surface regression tests ----------


@pytest.mark.asyncio
async def test_status_works_against_async_graph_client_shape():
    """The real GraphClient's list_document_nodes is async. SyncService.status
    must await it — not iterate a coroutine."""
    sync = _make_sync(
        store_rows=[
            {"file_path": "a.md", "frontmatter": {"title": "A"}},
            {"file_path": "b.md", "frontmatter": {}},
        ]
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # RuntimeWarning → error
        status = await sync.status()
    assert status.graph_enabled is True
    assert status.lancedb_count == 2
    assert status.graph_count == 0  # graph is empty, drift=2
    assert status.drift == 2


@pytest.mark.asyncio
async def test_reconcile_awaits_upsert_on_async_graph_client():
    sync = _make_sync(
        store_rows=[
            {"file_path": "a.md", "frontmatter": {"title": "A"}},
            {"file_path": "b.md", "frontmatter": {}},
        ]
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        status = await sync.reconcile()
    assert status.drift == 0
    # The backing fake recorded both upserts — proving the adapter awaited
    # the coroutine rather than silently dropping it.
    adapter_client: AsyncGraphClientFake = sync._graph._client  # type: ignore[attr-defined]
    assert sorted(doc_id for _kb, doc_id in adapter_client.upserts) == ["a.md", "b.md"]


@pytest.mark.asyncio
async def test_reconcile_deletes_stale_nodes_on_async_client():
    sync = _make_sync(store_rows=[{"file_path": "a.md", "frontmatter": {}}])
    # Seed the fake with a stale node
    client: AsyncGraphClientFake = sync._graph._client  # type: ignore[attr-defined]
    client.documents["stale.md"] = {"id": "stale.md"}

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        status = await sync.reconcile()

    assert status.drift == 0
    assert sorted(doc_id for _kb, doc_id in client.deletes) == ["stale.md"]


@pytest.mark.asyncio
async def test_upsert_one_awaits_async_client():
    sync = _make_sync(store_rows=[])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await sync.upsert_one({"id": "x.md", "title": "X", "path": "x.md"})
    client: AsyncGraphClientFake = sync._graph._client  # type: ignore[attr-defined]
    assert client.upserts == [("local", "x.md")]


@pytest.mark.asyncio
async def test_delete_one_awaits_async_client():
    sync = _make_sync(store_rows=[])
    client: AsyncGraphClientFake = sync._graph._client  # type: ignore[attr-defined]
    client.documents["x.md"] = {"id": "x.md"}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await sync.delete_one("x.md")
    assert client.deletes == [("local", "x.md")]


# ---------- Consumer-path tests ----------


@pytest.mark.asyncio
async def test_startup_reconcile_completes_without_warnings_or_errors():
    """Drives the same path that dev-server's lifespan hits on boot."""
    sync = _make_sync(
        store_rows=[{"file_path": "a.md", "frontmatter": {}}],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await run_startup_reconcile(sync)
    client: AsyncGraphClientFake = sync._graph._client  # type: ignore[attr-defined]
    assert sorted(doc_id for _kb, doc_id in client.upserts) == ["a.md"]


@pytest.mark.asyncio
async def test_finalize_indexed_document_awaits_upsert_one():
    """BackgroundIndexer's ingest hook: finalize_indexed_document must
    await SyncService.upsert_one (both live inside async BackgroundIndexer
    methods)."""
    sync = _make_sync(store_rows=[])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await finalize_indexed_document(sync, {"id": "y.md", "title": "Y", "path": "y.md"})
    client: AsyncGraphClientFake = sync._graph._client  # type: ignore[attr-defined]
    assert client.upserts == [("local", "y.md")]


@pytest.mark.asyncio
async def test_finalize_deleted_document_awaits_delete_one():
    sync = _make_sync(store_rows=[])
    client: AsyncGraphClientFake = sync._graph._client  # type: ignore[attr-defined]
    client.documents["y.md"] = {"id": "y.md"}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await finalize_deleted_document(sync, "y.md")
    assert client.deletes == [("local", "y.md")]


# ---------- HTTP endpoint tests ----------


def _endpoint_app(sync: SyncService) -> FastAPI:
    app = FastAPI()
    app.state.sync = sync
    app.include_router(api_router)
    return app


def test_sync_status_endpoint_works_against_async_graph_client():
    """/sync/status must not raise when backed by an async GraphClient."""
    sync = _make_sync(
        store_rows=[{"file_path": "a.md", "frontmatter": {}}],
    )
    app = _endpoint_app(sync)
    client = TestClient(app)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        resp = client.get("/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["graph_enabled"] is True
    assert body["lancedb_count"] == 1
    assert body["drift"] == 1


def test_sync_reconcile_endpoint_heals_drift():
    sync = _make_sync(
        store_rows=[{"file_path": "a.md", "frontmatter": {}}],
    )
    app = _endpoint_app(sync)
    client = TestClient(app)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        resp = client.post("/sync/reconcile")
    assert resp.status_code == 200
    assert resp.json()["drift"] == 0


def test_sync_reconcile_endpoint_409_when_graph_disabled():
    sync = _make_sync(store_rows=[], graph_enabled=False)
    app = _endpoint_app(sync)
    client = TestClient(app)
    resp = client.post("/sync/reconcile")
    assert resp.status_code == 409


# ---------- Disabled-graph short-circuit (no client present) ----------


@pytest.mark.asyncio
async def test_status_when_graph_disabled_returns_lancedb_count_as_drift():
    sync = _make_sync(
        store_rows=[
            {"file_path": "a.md", "frontmatter": {}},
            {"file_path": "b.md", "frontmatter": {}},
        ],
        graph_enabled=False,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        status = await sync.status()
    assert status.graph_enabled is False
    assert status.lancedb_count == 2
    assert status.graph_count == 0
    assert status.drift == 2


@pytest.mark.asyncio
async def test_upsert_one_is_noop_when_graph_disabled():
    sync = _make_sync(store_rows=[], graph_enabled=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await sync.upsert_one({"id": "z.md", "title": "Z", "path": "z.md"})
    # nothing to assert on the client because there is no client — the
    # point is that upsert_one returned cleanly without exploding.


@pytest.mark.asyncio
async def test_reconcile_raises_when_graph_disabled():
    sync = _make_sync(store_rows=[], graph_enabled=False)
    with pytest.raises(RuntimeError, match="graph is disabled"):
        await sync.reconcile()
