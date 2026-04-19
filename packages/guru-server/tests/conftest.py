"""Shared pytest fixtures for guru-server tests."""

from __future__ import annotations

import pytest

from guru_server.app import create_app
from guru_server.sync import SyncService

# ---------------------------------------------------------------------------
# Fake adapters (mirrors FakeLanceStore / FakeGraphBackend from test_sync_service.py
# but kept local so conftest is self-contained).
# ---------------------------------------------------------------------------


class _FakeLanceStore:
    def __init__(self, ids: list[str]):
        self._ids = list(ids)
        self._docs = {i: {"id": i, "title": i, "path": i} for i in ids}

    def list_document_ids(self) -> list[str]:
        return list(self._ids)

    def get_document(self, doc_id: str) -> dict:
        return self._docs.get(doc_id, {"id": doc_id, "title": doc_id, "path": doc_id})


class _FakeGraphBackend:
    def __init__(self, ids: list[str], enabled: bool = True):
        self._ids = set(ids)
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    def list_document_node_ids(self, kb: str) -> list[str]:
        return list(self._ids)

    def upsert_document_node(self, kb: str, document: dict) -> None:
        self._ids.add(document["id"])

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        self._ids.discard(doc_id)


# ---------------------------------------------------------------------------
# App fixtures for sync endpoint tests
# ---------------------------------------------------------------------------


def _make_app_with_sync(lance_ids: list[str], graph_ids: list[str], graph_enabled: bool):
    """Build a minimal FastAPI app whose state.sync is wired to fake adapters."""
    from unittest.mock import MagicMock

    mock_store = MagicMock()
    mock_store.chunk_count.return_value = 0
    mock_store.document_count.return_value = len(lance_ids)
    mock_store.list_documents.return_value = []
    mock_store.get_document.return_value = None
    mock_store.list_document_ids.return_value = lance_ids

    app = create_app(store=mock_store, auto_index=False)

    # Override app.state.sync with one backed by our fake adapters.
    lance = _FakeLanceStore(ids=lance_ids)
    graph = _FakeGraphBackend(ids=graph_ids, enabled=graph_enabled)
    app.state.sync = SyncService(kb="test-kb", lance=lance, graph=graph)

    return app


@pytest.fixture
def test_app_with_seed():
    """App with 2 LanceDB docs, 1 graph doc (drift=1), graph enabled."""
    return _make_app_with_sync(
        lance_ids=["doc-a", "doc-b"],
        graph_ids=["doc-a"],
        graph_enabled=True,
    )


@pytest.fixture
def test_app_graph_disabled():
    """App with graph disabled — reconcile must return 409."""
    return _make_app_with_sync(
        lance_ids=["doc-a"],
        graph_ids=[],
        graph_enabled=False,
    )
