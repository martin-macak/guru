"""Ingestion routes consumed by guru-server. Not exposed to MCP.

Endpoints:
- POST /ingest/parse-result?kb_name=...  — apply ParseResultPayload
- DELETE /ingest/documents/{doc_id}?kb_name=...  — remove Document + subtree
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from guru_core.graph_types import ParseResultPayload

from ..services.ingest_service import IngestService

router = APIRouter()


def _svc(request: Request) -> IngestService:
    return IngestService(backend=request.app.state.backend)


@router.post("/ingest/parse-result", status_code=status.HTTP_204_NO_CONTENT)
def submit_parse_result(
    payload: ParseResultPayload,
    request: Request,
    kb_name: str,
) -> Response:
    _svc(request).submit(kb_name, payload)
    return Response(status_code=204)


@router.delete(
    "/ingest/documents/{doc_id:path}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    doc_id: str,
    request: Request,
    kb_name: str,
) -> Response:
    _svc(request).delete_document(kb_name, doc_id)
    return Response(status_code=204)
