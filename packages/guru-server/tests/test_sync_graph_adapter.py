from __future__ import annotations

from guru_server.sync import GraphSyncAdapter


class FakeGraphClient:
    def __init__(self, enabled=True, node_ids=None):
        self.enabled = enabled
        self._nodes = dict((n, {"id": n, "kind": "document"}) for n in node_ids or [])
        self.upserts = []
        self.deletes = []

    def is_available(self):
        return self.enabled

    def list_document_nodes(self, kb):
        return [{"id": n, "kind": "document"} for n in self._nodes]

    def upsert_document_node(self, kb, document):
        self._nodes[document["id"]] = {"id": document["id"], "kind": "document"}
        self.upserts.append((kb, document["id"]))

    def delete_document_node(self, kb, doc_id):
        self._nodes.pop(doc_id, None)
        self.deletes.append((kb, doc_id))


def test_adapter_passes_through_enable_flag():
    client = FakeGraphClient(enabled=False)
    adapter = GraphSyncAdapter(client=client)
    assert adapter.is_enabled() is False


def test_adapter_lists_document_node_ids():
    client = FakeGraphClient(enabled=True, node_ids=["a.md", "b.md"])
    adapter = GraphSyncAdapter(client=client)
    assert sorted(adapter.list_document_node_ids("local")) == ["a.md", "b.md"]


def test_adapter_upsert_and_delete_forward_to_client():
    client = FakeGraphClient(enabled=True)
    adapter = GraphSyncAdapter(client=client)
    adapter.upsert_document_node("local", {"id": "a.md", "title": "A", "path": "a.md"})
    adapter.delete_document_node("local", "a.md")
    assert client.upserts == [("local", "a.md")]
    assert client.deletes == [("local", "a.md")]
