from __future__ import annotations

import pytest

from guru_server.sync import GraphSyncAdapter


class FakeGraphClient:
    """Mirrors the real `guru_core.graph_client.GraphClient` surface.

    Document-node CRUD methods are ``async def`` — the adapter must await
    them. There is intentionally no ``is_available()`` method: GraphClient
    doesn't have one, and any adapter relying on it is broken.
    """

    def __init__(self, node_ids: list[str] | None = None) -> None:
        self._nodes = dict((n, {"id": n, "kind": "document"}) for n in node_ids or [])
        self.upserts: list[tuple[str, str]] = []
        self.deletes: list[tuple[str, str]] = []

    async def list_document_nodes(self, kb: str) -> list[dict]:
        return [{"id": n, "kind": "document"} for n in self._nodes]

    async def upsert_document_node(self, kb: str, document: dict) -> None:
        self._nodes[document["id"]] = {"id": document["id"], "kind": "document"}
        self.upserts.append((kb, document["id"]))

    async def delete_document_node(self, kb: str, doc_id: str) -> None:
        self._nodes.pop(doc_id, None)
        self.deletes.append((kb, doc_id))


def test_adapter_is_enabled_when_client_present():
    client = FakeGraphClient()
    adapter = GraphSyncAdapter(client=client)
    assert adapter.is_enabled() is True


def test_adapter_is_enabled_returns_false_when_client_is_none():
    adapter = GraphSyncAdapter(client=None)
    assert adapter.is_enabled() is False


class RealishGraphClientWithoutIsAvailable:
    """Surface-compatible fake that intentionally has no ``is_available``.

    Regression guard: an earlier adapter revision called
    ``self._client.is_available()`` which doesn't exist on the real
    GraphClient. This test would blow up with AttributeError if that bug
    returned.
    """

    async def list_document_nodes(self, kb):
        return []

    async def upsert_document_node(self, kb, document):
        pass

    async def delete_document_node(self, kb, doc_id):
        pass


def test_adapter_is_enabled_does_not_rely_on_is_available_method():
    client = RealishGraphClientWithoutIsAvailable()
    adapter = GraphSyncAdapter(client=client)
    assert adapter.is_enabled() is True


@pytest.mark.asyncio
async def test_adapter_lists_document_node_ids():
    client = FakeGraphClient(node_ids=["a.md", "b.md"])
    adapter = GraphSyncAdapter(client=client)
    assert sorted(await adapter.list_document_node_ids("local")) == ["a.md", "b.md"]


@pytest.mark.asyncio
async def test_adapter_upsert_and_delete_forward_to_client():
    client = FakeGraphClient()
    adapter = GraphSyncAdapter(client=client)
    await adapter.upsert_document_node("local", {"id": "a.md", "title": "A", "path": "a.md"})
    await adapter.delete_document_node("local", "a.md")
    assert client.upserts == [("local", "a.md")]
    assert client.deletes == [("local", "a.md")]
