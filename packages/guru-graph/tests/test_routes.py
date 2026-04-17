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


def _v1_headers() -> dict[str, str]:
    return {PROTOCOL_HEADER: PROTOCOL_VERSION}


def test_health_returns_ok(client: TestClient):
    r = client.get("/health", headers=_v1_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["graph_reachable"] is True
    assert body["backend"] == "fake"
    assert body["schema_version"] == 1


def test_version_returns_metadata(client: TestClient):
    r = client.get("/version", headers=_v1_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["protocol_version"] == PROTOCOL_VERSION
    assert body["backend"] == "fake"
    assert body["schema_version"] == 1


def test_protocol_major_mismatch_returns_426(client: TestClient):
    r = client.get("/health", headers={PROTOCOL_HEADER: "99.0.0"})
    assert r.status_code == 426
    assert "supported" in r.json()


def test_missing_protocol_header_is_accepted_for_backward_compat(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200


def test_upsert_kb_returns_201(client: TestClient):
    r = client.post(
        "/kbs",
        json={
            "name": "alpha",
            "project_root": "/tmp/a",
            "tags": ["app"],
            "metadata": {},
        },
        headers=_v1_headers(),
    )
    assert r.status_code == 201
    assert r.json()["name"] == "alpha"


def test_get_kb_missing_returns_404(client: TestClient):
    r = client.get("/kbs/missing", headers=_v1_headers())
    assert r.status_code == 404


def test_list_kbs_with_prefix(client: TestClient):
    for n in ("alpha", "alpine", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/tmp/{n}"}, headers=_v1_headers())
    r = client.get("/kbs?prefix=al", headers=_v1_headers())
    assert r.status_code == 200
    names = [n["name"] for n in r.json()]
    assert set(names) == {"alpha", "alpine"}


def test_delete_kb(client: TestClient):
    client.post("/kbs", json={"name": "x", "project_root": "/x"}, headers=_v1_headers())
    r = client.delete("/kbs/x", headers=_v1_headers())
    assert r.status_code == 204
    r2 = client.delete("/kbs/x", headers=_v1_headers())
    assert r2.status_code == 404


def test_create_link_requires_endpoints(client: TestClient):
    client.post("/kbs", json={"name": "alpha", "project_root": "/a"}, headers=_v1_headers())
    r = client.post(
        "/kbs/alpha/links", json={"to_kb": "beta", "kind": "depends_on"}, headers=_v1_headers()
    )
    assert r.status_code == 404


def test_create_and_list_link(client: TestClient):
    for n in ("alpha", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/{n}"}, headers=_v1_headers())
    r = client.post(
        "/kbs/alpha/links", json={"to_kb": "beta", "kind": "depends_on"}, headers=_v1_headers()
    )
    assert r.status_code == 201
    r2 = client.get("/kbs/alpha/links?direction=out", headers=_v1_headers())
    assert r2.status_code == 200
    body = r2.json()
    assert len(body) == 1
    assert body[0]["to_kb"] == "beta"
    assert body[0]["kind"] == "depends_on"


def test_unknown_link_kind_rejected(client: TestClient):
    for n in ("alpha", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/{n}"}, headers=_v1_headers())
    r = client.post(
        "/kbs/alpha/links", json={"to_kb": "beta", "kind": "sorta_related"}, headers=_v1_headers()
    )
    assert r.status_code == 422
    body = r.json()
    assert "depends_on" in str(body)


def test_delete_link(client: TestClient):
    for n in ("alpha", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/{n}"}, headers=_v1_headers())
    client.post(
        "/kbs/alpha/links", json={"to_kb": "beta", "kind": "depends_on"}, headers=_v1_headers()
    )
    r = client.delete("/kbs/alpha/links/beta/depends_on", headers=_v1_headers())
    assert r.status_code == 204


def test_query_route_accepts_read_only(client: TestClient):
    r = client.post(
        "/query",
        json={"cypher": "MATCH (n) RETURN n", "params": {}, "read_only": True},
        headers=_v1_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert "columns" in body and "rows" in body and "elapsed_ms" in body


def test_query_route_accepts_write(client: TestClient):
    r = client.post(
        "/query",
        json={"cypher": "CREATE (n:X)", "params": {}, "read_only": False},
        headers=_v1_headers(),
    )
    assert r.status_code == 200
