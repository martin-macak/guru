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


def test_adapter_is_enabled_when_client_present():
    client = FakeGraphClient(enabled=True)
    adapter = GraphSyncAdapter(client=client)
    assert adapter.is_enabled() is True


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


class RealishGraphClient:
    """Mirrors the public surface of `guru_core.graph_client.GraphClient`.

    The real client does NOT define `is_available()` — the adapter must not
    depend on that method. This fake carries the doc-node CRUD methods the
    adapter actually needs (and nothing else) so a bad adapter implementation
    that calls a non-existent method on the client will blow up here with
    AttributeError, exactly like it does against the real GraphClient in dev.
    """

    def list_document_nodes(self, kb):  # matches real GraphClient signature
        return []

    def upsert_document_node(self, kb, document):
        pass

    def delete_document_node(self, kb, doc_id):
        pass


def test_adapter_is_enabled_does_not_rely_on_is_available_method():
    """Regression guard: the real GraphClient has no is_available() method.

    Before the fix, `is_enabled()` called `self._client.is_available()`,
    which raised AttributeError whenever a real GraphClient was wired in
    (crashing startup reconcile, /sync/status, and the ingest hook).
    """
    client = RealishGraphClient()
    adapter = GraphSyncAdapter(client=client)
    assert adapter.is_enabled() is True  # client is not None → adapter is enabled


def test_adapter_is_enabled_returns_false_when_client_is_none():
    adapter = GraphSyncAdapter(client=None)
    assert adapter.is_enabled() is False
