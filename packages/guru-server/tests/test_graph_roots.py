from fastapi.testclient import TestClient


def test_graph_roots_returns_federation_and_kbs(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.get("/graph/roots")
    assert resp.status_code == 200
    body = resp.json()
    assert body["federation_root"] == {"id": "federation", "label": "Federation"}
    assert isinstance(body["kbs"], list)
    assert len(body["kbs"]) >= 1
    assert {"name", "project_root"} <= set(body["kbs"][0].keys())


def test_graph_roots_returns_410_when_graph_disabled(test_app_graph_disabled):
    client = TestClient(test_app_graph_disabled)
    resp = client.get("/graph/roots")
    assert resp.status_code == 410
    assert resp.json()["detail"] == "graph is disabled"
