from __future__ import annotations

import asyncio

import pytest

from guru_server.sync import SyncService


class FakeLanceStore:
    def __init__(self, ids: list[str]):
        self._ids = list(ids)

    def list_document_ids(self) -> list[str]:
        return list(self._ids)

    def get_document(self, doc_id: str) -> dict:
        return {"id": doc_id, "title": doc_id, "path": doc_id}


class FakeGraphBackend:
    """In-memory GraphBackend with async CRUD methods matching the Protocol.

    ``is_enabled`` stays sync (matches the Protocol); the three I/O methods
    are ``async def`` so SyncService exercises the real await contract.
    """

    def __init__(self, kb: str, ids: list[str] | None = None, enabled: bool = True):
        self.kb = kb
        self._ids = set(ids or [])
        self.enabled = enabled
        self.upserts: list[str] = []
        self.deletes: list[str] = []

    def is_enabled(self) -> bool:
        return self.enabled

    async def list_document_node_ids(self, kb: str) -> list[str]:
        assert kb == self.kb
        return list(self._ids)

    async def upsert_document_node(self, kb: str, document: dict) -> None:
        assert kb == self.kb
        self._ids.add(document["id"])
        self.upserts.append(document["id"])

    async def delete_document_node(self, kb: str, doc_id: str) -> None:
        assert kb == self.kb
        self._ids.discard(doc_id)
        self.deletes.append(doc_id)


@pytest.mark.asyncio
async def test_reconcile_heals_missing_and_stale_nodes():
    lance = FakeLanceStore(ids=["a", "b", "c"])
    graph = FakeGraphBackend(kb="local", ids=["b", "c", "d"])  # missing a, stale d
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = await svc.reconcile()

    assert graph.upserts == ["a"]
    assert graph.deletes == ["d"]
    assert status.lancedb_count == 3
    assert status.graph_count == 3
    assert status.drift == 0
    assert status.graph_enabled is True


@pytest.mark.asyncio
async def test_status_without_reconcile_reports_drift():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local", ids=["b"])
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = await svc.status()
    assert status.lancedb_count == 2
    assert status.graph_count == 1
    assert status.drift == 1


@pytest.mark.asyncio
async def test_status_when_graph_disabled_sets_flag_and_drift_to_lancedb_count():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local", ids=[], enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = await svc.status()
    assert status.graph_enabled is False
    assert status.lancedb_count == 2
    assert status.graph_count == 0
    assert status.drift == 2


@pytest.mark.asyncio
async def test_reconcile_raises_when_graph_disabled():
    lance = FakeLanceStore(ids=["a"])
    graph = FakeGraphBackend(kb="local", enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)

    with pytest.raises(RuntimeError, match="graph is disabled"):
        await svc.reconcile()


@pytest.mark.asyncio
async def test_upsert_one_forwards_when_enabled():
    lance = FakeLanceStore(ids=[])
    graph = FakeGraphBackend(kb="local")
    svc = SyncService(kb="local", lance=lance, graph=graph)
    await svc.upsert_one({"id": "a.md", "title": "A", "path": "a.md"})
    assert graph.upserts == ["a.md"]


@pytest.mark.asyncio
async def test_upsert_one_noop_when_disabled():
    lance = FakeLanceStore(ids=[])
    graph = FakeGraphBackend(kb="local", enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)
    await svc.upsert_one({"id": "a.md", "title": "A", "path": "a.md"})
    assert graph.upserts == []


@pytest.mark.asyncio
async def test_delete_one_forwards_when_enabled():
    lance = FakeLanceStore(ids=[])
    graph = FakeGraphBackend(kb="local", ids=["a.md"])
    svc = SyncService(kb="local", lance=lance, graph=graph)
    await svc.delete_one("a.md")
    assert graph.deletes == ["a.md"]


@pytest.mark.asyncio
async def test_reconcile_is_serialised_per_kb():
    """Two concurrent reconciles must not interleave — the asyncio.Lock
    serialises them. We use an asyncio.Event inside the fake's upsert path
    to pin the first reconcile mid-flight, then assert the second one is
    queued behind it."""
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local")
    svc = SyncService(kb="local", lance=lance, graph=graph)

    entered = asyncio.Event()
    release = asyncio.Event()
    original_upsert = graph.upsert_document_node

    async def slow_upsert(kb: str, document: dict) -> None:
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=2)
        await original_upsert(kb, document)

    graph.upsert_document_node = slow_upsert  # type: ignore[method-assign]

    first = asyncio.create_task(svc.reconcile())
    await asyncio.wait_for(entered.wait(), timeout=2)

    second = asyncio.create_task(svc.reconcile())
    # Give the second task a chance to reach the lock — it must block.
    await asyncio.sleep(0.05)
    assert not second.done(), "second reconcile should block on the lock"

    release.set()
    await asyncio.wait_for(first, timeout=2)
    await asyncio.wait_for(second, timeout=2)
