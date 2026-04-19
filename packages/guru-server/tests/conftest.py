"""Shared pytest fixtures for guru-server tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

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
    mock_store = MagicMock()
    mock_store.chunk_count.return_value = 0
    mock_store.document_count.return_value = len(lance_ids)
    mock_store.list_documents.return_value = []
    mock_store.get_document.return_value = None
    mock_store.list_document_ids.return_value = lance_ids
    # search() returns rows with file_path, content, score fields
    mock_store.search.return_value = [
        {
            "file_path": "readme.md",
            "content": "This is a readme document",
            "header_breadcrumb": "README",
            "score": 0.95,
        }
    ]

    mock_embedder = MagicMock()
    mock_embedder.check_health = AsyncMock()
    mock_embedder.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)

    # Override app.state.sync with one backed by our fake adapters.
    lance = _FakeLanceStore(ids=lance_ids)
    graph = _FakeGraphBackend(ids=graph_ids, enabled=graph_enabled)
    app.state.sync = SyncService(kb="test-kb", lance=lance, graph=graph)

    return app


def _make_kb_node(name: str = "test-kb", project_root: str = "/tmp/test") -> MagicMock:
    """Build a mock KbNode with the fields tested by graph_roots tests."""
    from guru_core.graph_types import KbNode

    now = datetime.now(UTC)
    return KbNode(
        name=name,
        project_root=project_root,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def test_app_with_seed():
    """App with 2 LanceDB docs, 1 graph doc (drift=1), graph enabled.

    Also wires a mock graph_client that returns a KB node for /graph/roots
    and a realistic ArtifactNode for describe_artifact("doc:a.md").
    """
    from guru_core.graph_types import ArtifactLink, ArtifactLinkKind, ArtifactNode

    app = _make_app_with_sync(
        lance_ids=["doc-a", "doc-b"],
        graph_ids=["doc-a"],
        graph_enabled=True,
    )

    # Patch the mock store to return a realistic document for a.md
    app.state.store.get_document.side_effect = lambda path: (
        {
            "file_path": path,
            "content": "Hello world this is content",
            "frontmatter": {"tags": ["foo", "bar"]},
            "labels": ["foo"],
            "chunk_count": 3,
        }
        if path == "a.md"
        else None
    )

    # Wire a mock graph client that supports /graph/roots and describe_artifact.
    mock_graph_client = MagicMock()
    mock_graph_client.get_kb = AsyncMock(return_value=_make_kb_node())
    mock_graph_client.describe_artifact = AsyncMock(
        return_value=ArtifactNode(
            id="doc:a.md",
            label="Document",
            properties={"kind": "document", "name": "a.md"},
            annotations=[],
            links_out=[
                ArtifactLink(
                    from_id="doc:a.md",
                    to_id="doc:b.md",
                    kind=ArtifactLinkKind.IMPORTS,
                    created_at=datetime.now(UTC),
                    author=None,
                )
            ],
            links_in=[],
        )
    )
    app.state.graph_client = mock_graph_client
    app.state.project_name = "test-kb"
    return app


@pytest.fixture
def test_app_graph_disabled():
    """App with graph disabled — reconcile must return 409, /graph/roots returns 410."""
    app = _make_app_with_sync(
        lance_ids=["doc-a"],
        graph_ids=[],
        graph_enabled=False,
    )
    # Patch the mock store to return a realistic document for a.md
    app.state.store.get_document.side_effect = lambda path: (
        {
            "file_path": path,
            "content": "Hello world",
            "frontmatter": {},
            "labels": [],
            "chunk_count": 1,
        }
        if path == "a.md"
        else None
    )
    # graph_client is None when disabled
    app.state.graph_client = None
    return app


@pytest.fixture
def test_app_with_mixed_graph():
    """App whose mock graph client returns both document-kind and artifact-kind neighbor nodes.

    Used to verify that /graph/neighbors filters out non-document nodes.
    """
    app = _make_app_with_sync(
        lance_ids=["doc-a"],
        graph_ids=["doc-a"],
        graph_enabled=True,
    )
    # Return a payload with one document node and one code-artifact node.
    neighbors_payload = MagicMock()
    neighbors_payload.model_dump.return_value = {
        "node_id": "doc:a.md",
        "nodes": [
            {
                "id": "doc:a.md",
                "label": "Document",
                "kind": "document",
                "properties": {"kind": "document", "name": "a.md"},
                "annotations": [],
                "links_out": [],
                "links_in": [],
            },
            {
                "id": "code:MyClass",
                "label": "Class",
                "kind": "artifact",
                "properties": {"kind": "artifact", "name": "MyClass"},
                "annotations": [],
                "links_out": [],
                "links_in": [],
            },
        ],
        "edges": [
            {
                "from_id": "doc:a.md",
                "to_id": "code:MyClass",
                "rel_type": "RELATES",
                "kind": "references",
                "properties": {},
            }
        ],
    }
    mock_graph_client = MagicMock()
    mock_graph_client.neighbors = AsyncMock(return_value=neighbors_payload)
    app.state.graph_client = mock_graph_client
    return app
