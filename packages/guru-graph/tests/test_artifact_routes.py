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
    backend.seed_artifact(
        node_id="alpha::pkg.module.Widget",
        label="Class",
        properties={"name": "Widget", "qualname": "pkg.module.Widget", "kb_name": "alpha"},
    )
    backend.seed_artifact(
        node_id="alpha::pkg.module.Helper",
        label="Class",
        properties={"name": "Helper", "qualname": "pkg.module.Helper", "kb_name": "alpha"},
    )
    backend.seed_artifact_edge(
        from_id="alpha::pkg.module.Widget",
        to_id="alpha::pkg.module.Helper",
        rel_type="RELATES",
        kind="references",
    )
    app = create_app(backend=backend)
    with TestClient(app) as c:
        yield c
    backend.stop()


def _headers() -> dict[str, str]:
    return {PROTOCOL_HEADER: PROTOCOL_VERSION}


def test_get_artifact_returns_node(client: TestClient):
    response = client.get("/artifacts/alpha::pkg.module.Widget", headers=_headers())
    assert response.status_code == 200
    assert response.json()["id"] == "alpha::pkg.module.Widget"


def test_get_artifact_missing_returns_404(client: TestClient):
    response = client.get("/artifacts/alpha::missing", headers=_headers())
    assert response.status_code == 404


def test_get_neighbors_returns_payload(client: TestClient):
    response = client.get(
        "/artifacts/alpha::pkg.module.Widget/neighbors?direction=out&rel_type=RELATES&depth=1",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["node_id"] == "alpha::pkg.module.Widget"
    assert [node["id"] for node in body["nodes"]] == [
        "alpha::pkg.module.Widget",
        "alpha::pkg.module.Helper",
    ]


def test_find_artifacts_returns_matches(client: TestClient):
    response = client.post(
        "/artifacts/find",
        json={"name": "Wid", "label": "Class", "kb_name": "alpha", "limit": 5},
        headers=_headers(),
    )
    assert response.status_code == 200
    assert [node["id"] for node in response.json()] == ["alpha::pkg.module.Widget"]
