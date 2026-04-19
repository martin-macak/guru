from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing import FakeBackend
from guru_graph.versioning import PROTOCOL_HEADER, PROTOCOL_VERSION


@pytest.fixture
def client() -> TestClient:
    backend = FakeBackend()
    backend.start()
    backend.ensure_schema(target_version=1)
    app = create_app(backend=backend)
    with TestClient(app) as c:
        yield c
    backend.stop()


def _headers() -> dict[str, str]:
    return {PROTOCOL_HEADER: PROTOCOL_VERSION}


def test_submit_parse_result_creates_document_and_section(client: TestClient):
    response = client.post(
        "/ingest/parse-result?kb_name=alpha",
        json={
            "chunks_count": 1,
            "document": {
                "node_id": "alpha::docs/guide.md",
                "label": "Document",
                "properties": {"kb_name": "alpha", "relative_path": "docs/guide.md"},
            },
            "nodes": [
                {
                    "node_id": "alpha::docs/guide.md::Intro",
                    "label": "MarkdownSection",
                    "properties": {"kb_name": "alpha", "breadcrumb": "Intro"},
                }
            ],
            "edges": [
                {
                    "from_id": "alpha::docs/guide.md",
                    "to_id": "alpha::docs/guide.md::Intro",
                    "rel_type": "CONTAINS",
                    "properties": {},
                }
            ],
        },
        headers=_headers(),
    )
    assert response.status_code == 204

    describe = client.get("/artifacts/alpha::docs/guide.md::Intro", headers=_headers())
    assert describe.status_code == 200
    assert describe.json()["label"] == "MarkdownSection"


def test_delete_document_removes_document_subgraph(client: TestClient):
    client.post(
        "/ingest/parse-result?kb_name=alpha",
        json={
            "chunks_count": 1,
            "document": {
                "node_id": "alpha::docs/guide.md",
                "label": "Document",
                "properties": {"kb_name": "alpha", "relative_path": "docs/guide.md"},
            },
            "nodes": [
                {
                    "node_id": "alpha::docs/guide.md::Intro",
                    "label": "MarkdownSection",
                    "properties": {"kb_name": "alpha", "breadcrumb": "Intro"},
                }
            ],
            "edges": [
                {
                    "from_id": "alpha::docs/guide.md",
                    "to_id": "alpha::docs/guide.md::Intro",
                    "rel_type": "CONTAINS",
                    "properties": {},
                }
            ],
        },
        headers=_headers(),
    )

    response = client.delete(
        "/ingest/documents/alpha::docs/guide.md?kb_name=alpha",
        headers=_headers(),
    )
    assert response.status_code == 204

    describe = client.get("/artifacts/alpha::docs/guide.md::Intro", headers=_headers())
    assert describe.status_code == 404
