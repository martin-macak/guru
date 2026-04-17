from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.versioning import PROTOCOL_HEADER, PROTOCOL_VERSION

pytestmark = pytest.mark.real_neo4j


@pytest.fixture
def client(real_neo4j_backend) -> TestClient:
    real_neo4j_backend.ensure_schema(target_version=1)
    app = create_app(backend=real_neo4j_backend)
    with TestClient(app) as c:
        yield c


def _hdr() -> dict[str, str]:
    return {PROTOCOL_HEADER: PROTOCOL_VERSION}


def test_read_only_roundtrip(client: TestClient):
    r = client.post(
        "/query",
        json={"cypher": "RETURN 1 AS x, 'hi' AS y", "params": {}, "read_only": True},
        headers=_hdr(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["columns"] == ["x", "y"]
    assert body["rows"] == [[1, "hi"]]


def test_write_query_via_escape_hatch(client: TestClient):
    client.post(
        "/query",
        json={"cypher": "CREATE (:TempNode {v: $v})", "params": {"v": 42}, "read_only": False},
        headers=_hdr(),
    )
    r2 = client.post(
        "/query",
        json={"cypher": "MATCH (n:TempNode) RETURN n.v AS v", "params": {}, "read_only": True},
        headers=_hdr(),
    )
    assert r2.status_code == 200
    assert r2.json()["rows"] == [[42]]


def test_malformed_cypher_returns_structured_error(client: TestClient):
    r = client.post(
        "/query",
        json={"cypher": "THIS IS NOT CYPHER", "params": {}, "read_only": True},
        headers=_hdr(),
    )
    assert r.status_code == 500
    body = r.json()
    assert "detail" in body or "error" in body
