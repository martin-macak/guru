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
