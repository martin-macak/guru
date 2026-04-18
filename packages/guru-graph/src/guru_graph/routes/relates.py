"""Routes for artifact RELATES edges.

POST   /relates                           create (returns ArtifactLink)
DELETE /relates                           delete (204 / 404)
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from guru_core.graph_types import ArtifactLink, ArtifactLinkCreate, ArtifactUnlink

from ..services.relates_service import EndpointNotFoundError, RelatesService

router = APIRouter()


def _svc(request: Request) -> RelatesService:
    return RelatesService(backend=request.app.state.backend)


@router.post("/relates", response_model=ArtifactLink, status_code=status.HTTP_201_CREATED)
def create_relates(
    req: ArtifactLinkCreate,
    request: Request,
    x_guru_author: str = Header(default="user:unknown"),
) -> ArtifactLink:
    try:
        return _svc(request).create(req, author=x_guru_author)
    except EndpointNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/relates", status_code=status.HTTP_204_NO_CONTENT)
def delete_relates(req: ArtifactUnlink, request: Request) -> Response:
    deleted = _svc(request).delete(from_id=req.from_id, to_id=req.to_id, kind=req.kind)
    if not deleted:
        raise HTTPException(status_code=404, detail="link not found")
    return Response(status_code=204)
