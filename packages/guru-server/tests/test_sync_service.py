from __future__ import annotations

import threading
import time

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
    def __init__(self, kb: str, ids: list[str] | None = None, enabled: bool = True):
        self.kb = kb
        self._ids = set(ids or [])
        self.enabled = enabled
        self.upserts: list[str] = []
        self.deletes: list[str] = []

    def is_enabled(self) -> bool:
        return self.enabled

    def list_document_node_ids(self, kb: str) -> list[str]:
        assert kb == self.kb
        return list(self._ids)

    def upsert_document_node(self, kb: str, document: dict) -> None:
        assert kb == self.kb
        self._ids.add(document["id"])
        self.upserts.append(document["id"])

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        assert kb == self.kb
        self._ids.discard(doc_id)
        self.deletes.append(doc_id)


def test_reconcile_heals_missing_and_stale_nodes():
    lance = FakeLanceStore(ids=["a", "b", "c"])
    graph = FakeGraphBackend(kb="local", ids=["b", "c", "d"])  # missing a, stale d
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = svc.reconcile()

    assert graph.upserts == ["a"]
    assert graph.deletes == ["d"]
    assert status.lancedb_count == 3
    assert status.graph_count == 3
    assert status.drift == 0
    assert status.graph_enabled is True


def test_status_without_reconcile_reports_drift():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local", ids=["b"])
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = svc.status()
    assert status.lancedb_count == 2
    assert status.graph_count == 1
    assert status.drift == 1


def test_status_when_graph_disabled_sets_flag_and_drift_to_lancedb_count():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local", ids=[], enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = svc.status()
    assert status.graph_enabled is False
    assert status.lancedb_count == 2
    assert status.graph_count == 0
    assert status.drift == 2


def test_reconcile_raises_when_graph_disabled():
    lance = FakeLanceStore(ids=["a"])
    graph = FakeGraphBackend(kb="local", enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)

    with pytest.raises(RuntimeError, match="graph is disabled"):
        svc.reconcile()


def test_reconcile_is_serialised_per_kb():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local")
    svc = SyncService(kb="local", lance=lance, graph=graph)

    entered = threading.Event()
    release = threading.Event()
    original_upsert = graph.upsert_document_node

    def slow_upsert(kb, document):
        entered.set()
        release.wait(timeout=2)
        original_upsert(kb, document)

    graph.upsert_document_node = slow_upsert

    t = threading.Thread(target=svc.reconcile)
    t.start()
    assert entered.wait(timeout=2)

    start = time.monotonic()
    blocker = threading.Thread(target=svc.reconcile)
    blocker.start()
    time.sleep(0.1)
    assert blocker.is_alive(), "second reconcile should block on the lock"

    release.set()
    t.join(timeout=2)
    blocker.join(timeout=2)
    assert not blocker.is_alive()
    assert time.monotonic() - start < 5
