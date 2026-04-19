from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from guru_server.indexer import finalize_deleted_document, finalize_indexed_document


@pytest.mark.asyncio
async def test_finalize_upserts_graph_node_when_enabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = True
    sync.upsert_one = AsyncMock()
    document = {"id": "a.md", "title": "A", "path": "a.md"}
    await finalize_indexed_document(sync, document)
    sync.upsert_one.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_finalize_noop_when_disabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = False
    sync.upsert_one = AsyncMock()
    await finalize_indexed_document(sync, {"id": "a.md", "title": "A", "path": "a.md"})
    sync.upsert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_deleted_forwards_when_enabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = True
    sync.delete_one = AsyncMock()
    await finalize_deleted_document(sync, "a.md")
    sync.delete_one.assert_awaited_once_with("a.md")


@pytest.mark.asyncio
async def test_finalize_deleted_noop_when_disabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = False
    sync.delete_one = AsyncMock()
    await finalize_deleted_document(sync, "a.md")
    sync.delete_one.assert_not_awaited()
