"""Red-tests for /query error handling.

When the backend raises (e.g. Cypher syntax error), the route must translate
that into a structured 500 JSON response — NOT let the exception escape to
the client/TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing import FakeBackend
from guru_graph.versioning import PROTOCOL_HEADER, PROTOCOL_VERSION


class _RaisingBackend(FakeBackend):
    """FakeBackend whose Cypher surface raises a fake Neo4jError clone.

    We don't import neo4j.exceptions here so the test stays hermetic. The
    handler must catch *any* exception from backend.execute / execute_read,
    so a plain Exception subclass is sufficient to verify the contract.
    """

    def execute(self, cypher, params):
        raise RuntimeError("Invalid input 'THIS': expected MATCH, ...")

    def execute_read(self, cypher, params):
        raise RuntimeError("Invalid input 'THIS': expected MATCH, ...")


@pytest.fixture
def client() -> TestClient:
    backend = _RaisingBackend()
    backend.start()
    backend.ensure_schema(target_version=1)
    app = create_app(backend=backend)
    with TestClient(app) as c:
        yield c
    backend.stop()


def _hdr():
    return {PROTOCOL_HEADER: PROTOCOL_VERSION}


def test_query_route_translates_backend_error_to_500(client: TestClient):
    r = client.post(
        "/query",
        json={"cypher": "THIS IS NOT CYPHER", "params": {}, "read_only": True},
        headers=_hdr(),
    )
    assert r.status_code == 500
    body = r.json()
    assert "detail" in body or "error" in body


def test_query_route_error_body_is_json_not_plain_text(client: TestClient):
    r = client.post(
        "/query",
        json={"cypher": "whatever", "params": {}, "read_only": True},
        headers=_hdr(),
    )
    # Must be valid JSON (raises ValueError if not)
    assert isinstance(r.json(), dict)


def test_query_route_error_mentions_original_message(client: TestClient):
    r = client.post(
        "/query",
        json={"cypher": "bogus", "params": {}, "read_only": True},
        headers=_hdr(),
    )
    body_str = str(r.json())
    assert "Invalid input" in body_str
