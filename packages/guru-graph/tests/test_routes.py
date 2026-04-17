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
