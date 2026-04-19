from fastapi.testclient import TestClient


def test_neighbors_are_filtered_to_document_kind(test_app_with_mixed_graph):
    client = TestClient(test_app_with_mixed_graph)
    resp = client.get("/graph/neighbors/doc:a.md")
    assert resp.status_code == 200
    body = resp.json()
    kinds = {node["kind"] for node in body["nodes"]}
    assert kinds.issubset({"document", "kb"})
