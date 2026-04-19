"""MCP-facing graph proxy routes.

Every endpoint is a thin wrapper that:
  1) Short-circuits to 200 + body {"status":"graph_disabled"} if graph is off
     (i.e. ``app.state.graph_client is None``).
  2) Stamps X-Guru-Author based on the request's ``x-guru-mcp-client`` header
     (set by guru-mcp). Falls back to ``user:unknown``.
  3) Forces read_only=True on ``/graph/query`` regardless of body content.
  4) On GraphUnavailable from the client (daemon down / unreachable),
     returns 200 + ``{"status":"graph_disabled"}`` so MCP tools never see
     a failure - they degrade silently per design.

This is the read-out / write-in surface that guru-mcp talks to. The CLI
also uses this proxy for its read-only commands.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    AnnotationCreate,
    ArtifactFindQuery,
    ArtifactLinkCreate,
    ArtifactUnlink,
    CypherQuery,
    FederationRootNode,
    GraphRootsPayload,
    ReattachRequest,
)

router = APIRouter(prefix="/graph")


def _graph_disabled_body() -> dict:
    return {"status": "graph_disabled"}


def _author_from_headers(request: Request, explicit: str | None) -> str:
    if explicit:
        return explicit
    client = request.headers.get("x-guru-mcp-client")
    if client:
        return f"agent:{client}"
    return "user:unknown"


def _client_or_none(request: Request) -> GraphClient | None:
    return getattr(request.app.state, "graph_client", None)


@router.get("/describe/{node_id:path}")
async def proxy_describe(node_id: str, request: Request) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        node = await client.describe_artifact(node_id)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    if node is None:
        return JSONResponse(
            {"error": "not_found", "detail": f"node {node_id!r} not found"},
            status_code=404,
        )
    return JSONResponse(node.model_dump(mode="json"))


@router.get("/neighbors/{node_id:path}")
async def proxy_neighbors(
    node_id: str,
    request: Request,
    direction: Literal["in", "out", "both"] = "both",
    rel_type: Literal["CONTAINS", "RELATES", "both"] = "both",
    kind: str | None = None,
    depth: int = 1,
    limit: int = 50,
) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        result = await client.neighbors(
            node_id,
            direction=direction,
            rel_type=rel_type,
            kind=kind,
            depth=depth,
            limit=limit,
        )
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse(result.model_dump(mode="json"))


@router.post("/find")
async def proxy_find(q: ArtifactFindQuery, request: Request) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        results = await client.find_artifacts(q)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse([r.model_dump(mode="json") for r in results])


@router.post("/annotations")
async def proxy_create_annotation(
    body: AnnotationCreate,
    request: Request,
    x_guru_author: str | None = Header(default=None),
) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    author = _author_from_headers(request, x_guru_author)
    try:
        ann = await client.create_annotation(body, author=author)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse(ann.model_dump(mode="json"), status_code=201)


@router.delete("/annotations/{annotation_id}")
async def proxy_delete_annotation(annotation_id: str, request: Request) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        ok = await client.delete_annotation(annotation_id=annotation_id)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    if not ok:
        return JSONResponse(
            {"error": "not_found", "detail": f"annotation {annotation_id!r} not found"},
            status_code=404,
        )
    return JSONResponse({"deleted": True})


@router.post("/links")
async def proxy_create_link(
    body: ArtifactLinkCreate,
    request: Request,
    x_guru_author: str | None = Header(default=None),
) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    author = _author_from_headers(request, x_guru_author)
    try:
        link = await client.create_link(body, author=author)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse(link.model_dump(mode="json"), status_code=201)


@router.delete("/links")
async def proxy_delete_link(body: ArtifactUnlink, request: Request) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        ok = await client.delete_link(from_id=body.from_id, to_id=body.to_id, kind=body.kind)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    if not ok:
        return JSONResponse(
            {"error": "not_found", "detail": "link not found"},
            status_code=404,
        )
    return JSONResponse({"deleted": True})


@router.get("/orphans")
async def proxy_list_orphans(request: Request, limit: int = 50) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        orphans = await client.list_orphans(limit=limit)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse([o.model_dump(mode="json") for o in orphans])


@router.post("/orphans/{annotation_id}/reattach")
async def proxy_reattach_orphan(
    annotation_id: str, body: ReattachRequest, request: Request
) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        ann = await client.reattach_orphan(
            annotation_id=annotation_id, new_node_id=body.new_node_id
        )
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse(ann.model_dump(mode="json"))


@router.post("/query")
async def proxy_query(body: CypherQuery, request: Request) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        result = await client.graph_query(cypher=body.cypher, params=body.params)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse(result.model_dump(mode="json"))


@router.get("/roots", response_model=GraphRootsPayload)
async def graph_roots(request: Request) -> GraphRootsPayload:
    client = _client_or_none(request)
    if client is None:
        raise HTTPException(status_code=410, detail="graph is disabled")

    project_name = getattr(request.app.state, "project_name", None)
    try:
        local_kb = await client.get_kb(project_name) if project_name else None
    except GraphUnavailable as exc:
        raise HTTPException(status_code=410, detail="graph is disabled") from exc

    kbs = [local_kb] if local_kb is not None else []
    return GraphRootsPayload(federation_root=FederationRootNode(), kbs=kbs)
