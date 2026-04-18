"""Annotation routes.

POST   /annotations                       create (returns AnnotationNode)
DELETE /annotations/{id}                  delete (204 / 404)
GET    /annotations/orphans               list orphans (returns list[OrphanAnnotation])
POST   /annotations/{id}/reattach         reattach (returns AnnotationNode)
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from guru_core.graph_types import (
    AnnotationCreate,
    AnnotationKind,
    AnnotationNode,
    OrphanAnnotation,
    ReattachRequest,
)

from ..services.annotation_service import AnnotationService, TargetNotFoundError

router = APIRouter()


def _svc(request: Request) -> AnnotationService:
    return AnnotationService(backend=request.app.state.backend)


@router.post("/annotations", response_model=AnnotationNode, status_code=status.HTTP_201_CREATED)
def create_annotation(
    req: AnnotationCreate,
    request: Request,
    x_guru_author: str = Header(default="user:unknown"),
) -> AnnotationNode:
    try:
        return _svc(request).create(req, author=x_guru_author)
    except TargetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(annotation_id: str, request: Request) -> Response:
    if not _svc(request).delete(annotation_id=annotation_id):
        raise HTTPException(status_code=404, detail=f"annotation {annotation_id!r} not found")
    return Response(status_code=204)


@router.get("/annotations/orphans", response_model=list[OrphanAnnotation])
def list_orphans(request: Request, limit: int = 50) -> list[OrphanAnnotation]:
    rows = _svc(request).list_orphans(limit=limit)
    return [_row_to_orphan(r) for r in rows]


@router.post("/annotations/{annotation_id}/reattach", response_model=AnnotationNode)
def reattach_orphan(
    annotation_id: str,
    req: ReattachRequest,
    request: Request,
) -> AnnotationNode:
    try:
        ok = _svc(request).reattach(annotation_id=annotation_id, new_node_id=req.new_node_id)
    except TargetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"annotation {annotation_id!r} not found or not orphaned",
        )
    row = request.app.state.backend.get_annotation(annotation_id=annotation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="annotation missing post-reattach")
    return _row_to_node(row)


def _row_to_orphan(r: dict) -> OrphanAnnotation:
    return OrphanAnnotation(
        id=r["annotation_id"],
        kind=AnnotationKind(r["kind"]),
        body=r["body"],
        tags=list(r.get("tags") or []),
        author=r["author"],
        created_at=datetime.fromtimestamp(r["created_at"], tz=UTC),
        updated_at=datetime.fromtimestamp(r["updated_at"], tz=UTC),
        target_snapshot_json=r["target_snapshot_json"],
    )


def _row_to_node(r: dict) -> AnnotationNode:
    return AnnotationNode(
        id=r["annotation_id"],
        target_id=r.get("target_id"),
        target_label=r.get("target_label"),
        kind=AnnotationKind(r["kind"]),
        body=r["body"],
        tags=list(r.get("tags") or []),
        author=r["author"],
        created_at=datetime.fromtimestamp(r["created_at"], tz=UTC),
        updated_at=datetime.fromtimestamp(r["updated_at"], tz=UTC),
        target_snapshot_json=r["target_snapshot_json"],
    )
