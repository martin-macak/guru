"""Cypher escape-hatch route.

Trust boundary is the UDS file permission. No per-request auth. Writes to the
:Kb / :LINKS / :_Meta schema from here are unsandboxed and can break the
domain contract — documented, not enforced.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from guru_core.graph_types import CypherQuery, QueryResult

from ..services.query_service import QueryService

router = APIRouter()


@router.post("/query", response_model=QueryResult)
def run_query(req: CypherQuery, request: Request) -> QueryResult:
    svc = QueryService(backend=request.app.state.backend)
    return svc.run(req)
