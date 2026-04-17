"""KB CRUD and link routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status

from guru_core.graph_types import KbLink, KbLinkCreate, KbNode, KbUpsert, LinkKind

from ..services.kb_service import KbNotFoundError, KbService

router = APIRouter()


def _svc(request: Request) -> KbService:
    return KbService(backend=request.app.state.backend)


@router.post("/kbs", response_model=KbNode, status_code=status.HTTP_201_CREATED)
def upsert_kb(req: KbUpsert, request: Request) -> KbNode:
    return _svc(request).upsert(req)


@router.get("/kbs", response_model=list[KbNode])
def list_kbs(request: Request, prefix: str | None = None, tag: str | None = None) -> list[KbNode]:
    return _svc(request).list(prefix=prefix, tag=tag)


@router.get("/kbs/{name}", response_model=KbNode)
def get_kb(name: str, request: Request) -> KbNode:
    node = _svc(request).get(name)
    if node is None:
        raise HTTPException(status_code=404, detail=f"KB {name!r} not found")
    return node


@router.delete("/kbs/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kb(name: str, request: Request) -> Response:
    if not _svc(request).delete(name):
        raise HTTPException(status_code=404, detail=f"KB {name!r} not found")
    return Response(status_code=204)


@router.post("/kbs/{name}/links", response_model=KbLink, status_code=status.HTTP_201_CREATED)
def create_link(name: str, body: KbLinkCreate, request: Request) -> KbLink:
    try:
        return _svc(request).link(from_kb=name, req=body)
    except KbNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/kbs/{name}/links/{to}/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(name: str, to: str, kind: LinkKind, request: Request) -> Response:
    if not _svc(request).unlink(from_kb=name, to_kb=to, kind=kind):
        raise HTTPException(status_code=404, detail="link not found")
    return Response(status_code=204)


@router.get("/kbs/{name}/links", response_model=list[KbLink])
def list_links(
    name: str, request: Request, direction: Literal["in", "out", "both"] = "both"
) -> list[KbLink]:
    return _svc(request).list_links(name=name, direction=direction)
