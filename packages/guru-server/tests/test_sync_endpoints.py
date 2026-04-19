from __future__ import annotations

from fastapi.testclient import TestClient


def test_sync_status_shape(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.get("/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {
        "lancedb_count",
        "graph_count",
        "drift",
        "last_reconciled_at",
        "graph_enabled",
    }


def test_sync_reconcile_heals_drift(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post("/sync/reconcile")
    assert resp.status_code == 200
    assert resp.json()["drift"] == 0


def test_sync_reconcile_409_when_disabled(test_app_graph_disabled):
    client = TestClient(test_app_graph_disabled)
    resp = client.post("/sync/reconcile")
    assert resp.status_code == 409
