"""Cypher escape-hatch service.

read_only routes through backend.execute_read; writes through backend.execute.
We do NOT parse Cypher to sniff reads — the driver enforces it server-side.
"""

from __future__ import annotations

from guru_core.graph_types import CypherQuery, QueryResult

from ..backend.base import GraphBackend


class QueryService:
    def __init__(self, *, backend: GraphBackend):
        self._backend = backend

    def run(self, q: CypherQuery) -> QueryResult:
        params = dict(q.params or {})
        if q.read_only:
            res = self._backend.execute_read(q.cypher, params)
        else:
            res = self._backend.execute(q.cypher, params)
        return QueryResult(
            columns=list(res.columns),
            rows=[list(r) for r in res.rows],
            elapsed_ms=res.elapsed_ms,
        )
