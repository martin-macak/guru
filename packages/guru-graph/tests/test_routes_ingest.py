from __future__ import annotations

from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing.fake_backend import FakeBackend


def _body(doc_id: str, sub_ids: list[str]) -> dict:
    return {
        "chunks_count": len(sub_ids),
        "document": {
            "node_id": doc_id,
            "label": "Document",
            "properties": {"kb_name": "kb", "language": "markdown"},
        },
        "nodes": [
            {
                "node_id": i,
                "label": "MarkdownSection",
                "properties": {"kb_name": "kb", "breadcrumb": "X"},
            }
            for i in sub_ids
        ],
        "edges": [
            {
                "from_id": doc_id,
                "to_id": i,
                "rel_type": "CONTAINS",
                "kind": None,
                "properties": {},
            }
            for i in sub_ids
        ],
    }


def test_submit_parse_result_returns_204_and_creates_nodes():
    backend = FakeBackend()
    backend.start()
    app = create_app(backend=backend)
    client = TestClient(app)

    r = client.post(
        "/ingest/parse-result?kb_name=kb",
        json=_body("kb::x.md", ["kb::x.md::Title"]),
    )
    assert r.status_code == 204
    assert backend.get_artifact(node_id="kb::x.md") is not None
    assert backend.get_artifact(node_id="kb::x.md::Title") is not None


def test_delete_document_returns_204_and_removes_subtree():
    backend = FakeBackend()
    backend.start()
    app = create_app(backend=backend)
    client = TestClient(app)

    client.post(
        "/ingest/parse-result?kb_name=kb",
        json=_body("kb::x.md", ["kb::x.md::A"]),
    )
    r = client.delete("/ingest/documents/kb::x.md?kb_name=kb")
    assert r.status_code == 204
    assert backend.get_artifact(node_id="kb::x.md") is None
    assert backend.get_artifact(node_id="kb::x.md::A") is None


def test_submit_parse_result_rejects_invalid_payload():
    """Pydantic should reject a RELATES edge without kind."""
    backend = FakeBackend()
    backend.start()
    app = create_app(backend=backend)
    client = TestClient(app)

    bad = _body("kb::x.md", ["kb::x.md::A"])
    bad["edges"].append(
        {
            "from_id": "kb::x.md::A",
            "to_id": "kb::other",
            "rel_type": "RELATES",
            "kind": None,  # RELATES requires kind; validator must reject
            "properties": {},
        }
    )
    r = client.post("/ingest/parse-result?kb_name=kb", json=bad)
    assert r.status_code == 422  # FastAPI Pydantic validation
