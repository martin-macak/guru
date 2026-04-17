"""Cypher escape-hatch route.

Trust boundary is the UDS file permission. No per-request auth. Writes to the
:Kb / :LINKS / :_Meta schema from here are unsandboxed and can break the
domain contract — documented, not enforced.

Backend errors (invalid Cypher, constraint violations, driver errors) are
caught and returned as a structured 500 JSON body so consumers get a
predictable failure mode instead of an unhandled exception.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from guru_core.graph_types import CypherQuery, QueryResult

from ..services.query_service import QueryService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/query")
def run_query(req: CypherQuery, request: Request):
    """Execute raw Cypher.

    Returns 200 + QueryResult on success. Any backend exception is caught
    and translated to a 500 JSON body with the error message; this
    prevents unhandled exceptions from escaping to HTTP clients (and keeps
    the escape hatch predictable from guru-core's GraphClient).
    """
    svc = QueryService(backend=request.app.state.backend)
    try:
        result: QueryResult = svc.run(req)
    except Exception as e:
        logger.warning("/query backend error: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "error": "query_failed",
                "detail": str(e),
                "type": type(e).__name__,
            },
        )
    return JSONResponse(status_code=200, content=result.model_dump())
