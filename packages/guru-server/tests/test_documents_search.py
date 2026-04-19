from fastapi.testclient import TestClient


def test_documents_search_returns_ranked_hits(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post("/documents/search", json={"query": "readme", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "hits" in body
    assert len(body["hits"]) <= 5
    if body["hits"]:
        first = body["hits"][0]
        assert set(first.keys()) >= {"path", "title", "excerpt", "score"}
        assert isinstance(first["score"], float)


def test_documents_search_rejects_empty_query(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post("/documents/search", json={"query": "", "limit": 5})
    assert resp.status_code == 422
