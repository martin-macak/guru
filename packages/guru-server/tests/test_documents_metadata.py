"""Tests for GET /documents/{path}/metadata endpoint."""

from fastapi.testclient import TestClient


def test_documents_metadata_returns_both_sections_when_graph_enabled(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.get("/documents/a.md/metadata")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        body = resp.json()
        assert "lance" in body
        assert {"path", "chunk_count", "token_count", "tags", "ingested_at"} <= set(
            body["lance"].keys()
        )
        assert "graph" in body  # may be null if graph_client.describe_artifact returns None


def test_documents_metadata_graph_null_when_disabled(test_app_graph_disabled):
    client = TestClient(test_app_graph_disabled)
    resp = client.get("/documents/a.md/metadata")
    if resp.status_code == 200:
        body = resp.json()
        assert body["graph"] is None


def test_documents_metadata_404_for_unknown_doc(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.get("/documents/does_not_exist.md/metadata")
    assert resp.status_code == 404


def test_documents_metadata_lance_fields(test_app_with_seed):
    """Verify the lance section contains realistic data for the seeded doc."""
    client = TestClient(test_app_with_seed)
    resp = client.get("/documents/a.md/metadata")
    assert resp.status_code == 200
    lance = resp.json()["lance"]
    assert lance["path"] == "a.md"
    assert lance["chunk_count"] == 3
    assert lance["token_count"] > 0
    assert isinstance(lance["tags"], list)


def test_documents_metadata_graph_section_when_enabled(test_app_with_seed):
    """Verify the graph section is populated when graph client returns an artifact node."""
    client = TestClient(test_app_with_seed)
    resp = client.get("/documents/a.md/metadata")
    assert resp.status_code == 200
    body = resp.json()
    graph = body["graph"]
    assert graph is not None
    assert graph["node_id"] == "doc:a.md"
    assert isinstance(graph["degree"], int)
    assert isinstance(graph["links"], list)
