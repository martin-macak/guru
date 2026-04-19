from __future__ import annotations

import pytest

from guru_server.sync import LanceDocumentAdapter


class FakeStore:
    """Fake VectorStore returning real-shaped rows (with ``file_path``).

    Mirrors the real ``guru_server.storage.VectorStore`` row shape where
    ``list_documents()`` returns dicts keyed by ``file_path``/``frontmatter``/
    ``labels``/``chunk_count`` and ``get_document()`` returns the same plus
    ``content``.
    """

    def __init__(self, rows):
        self._rows = rows

    def list_documents(self):
        return [
            {
                "file_path": r["file_path"],
                "frontmatter": r.get("frontmatter", {}),
                "labels": r.get("labels", []),
                "chunk_count": r.get("chunk_count", 1),
            }
            for r in self._rows
        ]

    def get_document(self, file_path):
        for r in self._rows:
            if r["file_path"] == file_path:
                return {
                    "file_path": r["file_path"],
                    "content": r.get("content", ""),
                    "frontmatter": r.get("frontmatter", {}),
                    "labels": r.get("labels", []),
                    "chunk_count": r.get("chunk_count", 1),
                }
        return None


def test_adapter_enumerates_ids_from_file_path():
    store = FakeStore(
        [
            {"file_path": "a.md", "frontmatter": {"title": "A"}},
            {"file_path": "b.md", "frontmatter": {"title": "B"}},
        ]
    )
    adapter = LanceDocumentAdapter(store=store)
    assert adapter.list_document_ids() == ["a.md", "b.md"]


def test_adapter_returns_document_with_frontmatter_title():
    store = FakeStore([{"file_path": "a.md", "frontmatter": {"title": "A"}}])
    adapter = LanceDocumentAdapter(store=store)
    assert adapter.get_document("a.md") == {"id": "a.md", "title": "A", "path": "a.md"}


def test_adapter_falls_back_to_file_path_when_no_title():
    store = FakeStore([{"file_path": "notes/readme.md", "frontmatter": {}}])
    adapter = LanceDocumentAdapter(store=store)
    assert adapter.get_document("notes/readme.md") == {
        "id": "notes/readme.md",
        "title": "notes/readme.md",
        "path": "notes/readme.md",
    }


def test_adapter_handles_missing_frontmatter_key():
    class BareStore:
        def list_documents(self):
            return [{"file_path": "x.md"}]

        def get_document(self, file_path):
            if file_path == "x.md":
                return {"file_path": "x.md"}
            return None

    adapter = LanceDocumentAdapter(store=BareStore())
    assert adapter.list_document_ids() == ["x.md"]
    assert adapter.get_document("x.md") == {"id": "x.md", "title": "x.md", "path": "x.md"}


def test_adapter_raises_keyerror_when_document_missing():
    store = FakeStore([{"file_path": "a.md", "frontmatter": {"title": "A"}}])
    adapter = LanceDocumentAdapter(store=store)
    with pytest.raises(KeyError):
        adapter.get_document("missing.md")
