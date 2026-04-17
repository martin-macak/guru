from __future__ import annotations

from guru_core.graph_types import CypherQuery
from guru_graph.backend.base import CypherResult
from guru_graph.services.query_service import QueryService
from guru_graph.testing import FakeBackend


def test_query_service_routes_read_to_execute_read(monkeypatch):
    backend = FakeBackend()
    backend.start()
    calls = []

    def fake_read(cypher, params):
        calls.append(("read", cypher, params))
        return CypherResult(columns=["a"], rows=[[1]], elapsed_ms=0.0)

    monkeypatch.setattr(backend, "execute_read", fake_read)
    svc = QueryService(backend=backend)
    svc.run(CypherQuery(cypher="MATCH (n) RETURN n", params={}, read_only=True))
    assert calls and calls[0][0] == "read"


def test_query_service_routes_write_to_execute(monkeypatch):
    backend = FakeBackend()
    backend.start()
    calls = []

    def fake_write(cypher, params):
        calls.append(("write", cypher, params))
        return CypherResult(columns=[], rows=[], elapsed_ms=0.0)

    monkeypatch.setattr(backend, "execute", fake_write)
    svc = QueryService(backend=backend)
    svc.run(CypherQuery(cypher="CREATE (n:X) RETURN n", params={}, read_only=False))
    assert calls and calls[0][0] == "write"


def test_query_service_returns_query_result():
    backend = FakeBackend()
    backend.start()
    svc = QueryService(backend=backend)
    out = svc.run(CypherQuery(cypher="RETURN 1", params={}, read_only=True))
    assert out.columns == []
    assert out.rows == []
