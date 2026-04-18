"""Routes for artifact reads.

GET  /artifacts/{node_id}                  describe (returns ArtifactNode or 404)
GET  /artifacts/{node_id}/neighbors        walk neighbors (returns ArtifactNeighborsResult)
POST /artifacts/find                       search by filters (returns list[ArtifactNode])

Route ordering note: FastAPI matches routes in registration order. The `:path`
converter on `node_id` accepts slashes, so `GET /artifacts/{node_id:path}` would
swallow `GET /artifacts/{node_id:path}/neighbors` (matching `node_id` as
`"foo/neighbors"`) if the describe route is registered first. We therefore
register the more specific `/neighbors` route before the catch-all describe
route. `POST /artifacts/find` is dispatched on (method, path) so the GET
catch-all does not collide with it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status

from guru_core.graph_types import (
    ArtifactFindQuery,
    ArtifactNeighborsResult,
    ArtifactNode,
)

from ..services.artifact_service import ArtifactService

router = APIRouter()


def _svc(request: Request) -> ArtifactService:
    return ArtifactService(backend=request.app.state.backend)


@router.post("/artifacts/find", response_model=list[ArtifactNode], status_code=status.HTTP_200_OK)
def find(q: ArtifactFindQuery, request: Request) -> list[ArtifactNode]:
    return _svc(request).find(q)


@router.get(
    "/artifacts/{node_id:path}/neighbors",
    response_model=ArtifactNeighborsResult,
)
def neighbors(
    node_id: str,
    request: Request,
    direction: Literal["in", "out", "both"] = "both",
    rel_type: Literal["CONTAINS", "RELATES", "both"] = "both",
    kind: str | None = None,
    depth: int = 1,
    limit: int = 50,
) -> ArtifactNeighborsResult:
    return _svc(request).neighbors(
        node_id=node_id,
        direction=direction,
        rel_type=rel_type,
        kind=kind,
        depth=depth,
        limit=limit,
    )


@router.get("/artifacts/{node_id:path}", response_model=ArtifactNode)
def describe_artifact(node_id: str, request: Request) -> ArtifactNode:
    node = _svc(request).describe(node_id=node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"artifact {node_id!r} not found")
    return node
