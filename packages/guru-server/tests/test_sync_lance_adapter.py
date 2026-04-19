from __future__ import annotations

from guru_server.sync import LanceDocumentAdapter


class FakeStore:
    def __init__(self, rows):
        self._rows = rows

    def list_documents(self):
        return [{"path": r["path"], "title": r["title"]} for r in self._rows]

    def get_document(self, path):
        for r in self._rows:
            if r["path"] == path:
                return r
        return None


def test_adapter_enumerates_ids_from_store():
    store = FakeStore([{"path": "a.md", "title": "A"}, {"path": "b.md", "title": "B"}])
    adapter = LanceDocumentAdapter(store=store)
    assert adapter.list_document_ids() == ["a.md", "b.md"]


def test_adapter_returns_document_payload():
    store = FakeStore([{"path": "a.md", "title": "A"}])
    adapter = LanceDocumentAdapter(store=store)
    assert adapter.get_document("a.md") == {"id": "a.md", "title": "A", "path": "a.md"}
