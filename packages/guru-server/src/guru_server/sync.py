"""LanceDB ↔ graph sync invariant enforcement.

`SyncService` guarantees that for every document in LanceDB a corresponding
document-kind graph node exists under its local KB whenever the graph daemon
is enabled. The service is intentionally narrow: it knows nothing about HTTP,
FastAPI, or ingestion pipelines; those wire it up.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Protocol

from guru_core.graph_types import SyncStatus

logger = logging.getLogger(__name__)


class LanceStore(Protocol):
    def list_document_ids(self) -> list[str]: ...
    def get_document(self, doc_id: str) -> dict: ...


class GraphBackend(Protocol):
    def is_enabled(self) -> bool: ...
    def list_document_node_ids(self, kb: str) -> list[str]: ...
    def upsert_document_node(self, kb: str, document: dict) -> None: ...
    def delete_document_node(self, kb: str, doc_id: str) -> None: ...


class SyncService:
    def __init__(self, *, kb: str, lance: LanceStore, graph: GraphBackend) -> None:
        self._kb = kb
        self._lance = lance
        self._graph = graph
        self._lock = threading.Lock()
        self._last_reconciled_at: datetime | None = None

    def status(self) -> SyncStatus:
        lance_ids = set(self._lance.list_document_ids())
        lancedb_count = len(lance_ids)

        if not self._graph.is_enabled():
            return SyncStatus(
                lancedb_count=lancedb_count,
                graph_count=0,
                drift=lancedb_count,
                last_reconciled_at=self._last_reconciled_at,
                graph_enabled=False,
            )

        graph_ids = set(self._graph.list_document_node_ids(self._kb))
        drift = len(lance_ids.symmetric_difference(graph_ids))
        return SyncStatus(
            lancedb_count=lancedb_count,
            graph_count=len(graph_ids),
            drift=drift,
            last_reconciled_at=self._last_reconciled_at,
            graph_enabled=True,
        )

    def graph_enabled(self) -> bool:
        return self._graph.is_enabled()

    def upsert_one(self, document: dict) -> None:
        if not self._graph.is_enabled():
            return
        with self._lock:
            self._graph.upsert_document_node(self._kb, document)

    def delete_one(self, doc_id: str) -> None:
        if not self._graph.is_enabled():
            return
        with self._lock:
            self._graph.delete_document_node(self._kb, doc_id)

    def reconcile(self) -> SyncStatus:
        if not self._graph.is_enabled():
            raise RuntimeError("cannot reconcile: graph is disabled")

        with self._lock:
            lance_ids = set(self._lance.list_document_ids())
            graph_ids = set(self._graph.list_document_node_ids(self._kb))

            missing = sorted(lance_ids - graph_ids)
            stale = sorted(graph_ids - lance_ids)

            for doc_id in missing:
                doc = self._lance.get_document(doc_id)
                self._graph.upsert_document_node(self._kb, doc)

            for doc_id in stale:
                self._graph.delete_document_node(self._kb, doc_id)

            self._last_reconciled_at = datetime.now(tz=UTC)
            logger.info(
                "sync.reconcile kb=%s upserts=%d deletes=%d",
                self._kb,
                len(missing),
                len(stale),
            )
            return SyncStatus(
                lancedb_count=len(lance_ids),
                graph_count=len(lance_ids),
                drift=0,
                last_reconciled_at=self._last_reconciled_at,
                graph_enabled=True,
            )


class LanceDocumentAdapter:
    """Adapts the existing guru-server document store to the LanceStore protocol.

    The store-side API exposes a richer row shape; this adapter collapses it
    to the `(id, title, path)` triple that `SyncService` needs to mirror into
    the graph.
    """

    def __init__(self, *, store) -> None:
        self._store = store

    def list_document_ids(self) -> list[str]:
        return [row["path"] for row in self._store.list_documents()]

    def get_document(self, doc_id: str) -> dict:
        row = self._store.get_document(doc_id)
        if row is None:
            raise KeyError(doc_id)
        return {"id": row["path"], "title": row["title"], "path": row["path"]}


class GraphSyncAdapter:
    """Adapts `GraphClient` (from guru-core) to the GraphBackend protocol.

    Only document-kind nodes are visible through this adapter; parser-
    extracted code nodes belong to other subsystems (MCP/CLI) and must not
    be touched by SyncService.
    """

    def __init__(self, *, client) -> None:
        self._client = client

    def is_enabled(self) -> bool:
        if self._client is None:
            return False
        return bool(self._client.is_available())

    def list_document_node_ids(self, kb: str) -> list[str]:
        return [node["id"] for node in self._client.list_document_nodes(kb)]

    def upsert_document_node(self, kb: str, document: dict) -> None:
        self._client.upsert_document_node(kb, document)

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        self._client.delete_document_node(kb, doc_id)
