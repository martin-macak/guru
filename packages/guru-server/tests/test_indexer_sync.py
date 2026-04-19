from __future__ import annotations

from unittest.mock import MagicMock

from guru_server.indexer import finalize_deleted_document, finalize_indexed_document


def test_finalize_upserts_graph_node_when_enabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = True
    document = {"id": "a.md", "title": "A", "path": "a.md"}
    finalize_indexed_document(sync, document)
    sync.upsert_one.assert_called_once_with(document)


def test_finalize_noop_when_disabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = False
    finalize_indexed_document(sync, {"id": "a.md", "title": "A", "path": "a.md"})
    sync.upsert_one.assert_not_called()


def test_finalize_deleted_forwards_when_enabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = True
    finalize_deleted_document(sync, "a.md")
    sync.delete_one.assert_called_once_with("a.md")


def test_finalize_deleted_noop_when_disabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = False
    finalize_deleted_document(sync, "a.md")
    sync.delete_one.assert_not_called()
