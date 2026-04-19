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

import re
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
    QueryResult,
    ReattachRequest,
)

from .models import GraphEdgeOut, GraphNodeOut, GraphQueryResult

_WRITE_RE = re.compile(r"\b(create|merge|delete|set|remove|detach)\b", re.IGNORECASE)

_FEDERATION_ID = "federation"

router = APIRouter(prefix="/graph")

_WEB_ALLOWED_KINDS = {"document", "kb"}


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
    payload = result.model_dump(mode="json")

    # The `kind` field may appear either at the top level of a node (e.g. a
    # GraphNodeOut) or nested inside `properties` (e.g. a serialised
    # ArtifactNode). Accept either location so both code paths work.
    def _node_kind(n: dict) -> str | None:
        top_kind = n.get("kind")
        if top_kind is not None:
            return top_kind
        return (n.get("properties") or {}).get("kind")

    # Transform ArtifactNode-shaped dicts into the web-UI-expected format:
    # { id, label, kind, kb? }. The web canvas hook (useGraphCanvas) reads
    # n.id / n.label / n.kind / n.kb — not n.properties.kind.
    def _to_web_node(n: dict) -> dict:
        kind = _node_kind(n)
        props = n.get("properties") or {}
        return {
            "id": n["id"],
            "label": n.get("label", n["id"]),
            "kind": kind or "unknown",
            "kb": props.get("kb_name") or props.get("kb"),
        }

    # Transform edges: ArtifactNeighborsResult uses from_id/to_id; the web
    # canvas hook expects source/target.
    def _to_web_edge(e: dict) -> dict:
        return {
            "source": e.get("from_id", e.get("source", "")),
            "target": e.get("to_id", e.get("target", "")),
            "kind": e.get("kind") or e.get("rel_type") or "",
        }

    raw_nodes = payload.get("nodes", [])
    filtered_nodes = [_to_web_node(n) for n in raw_nodes if _node_kind(n) in _WEB_ALLOWED_KINDS]
    kept_ids = {n["id"] for n in filtered_nodes}
    raw_edges = payload.get("edges", [])
    web_edges = [
        _to_web_edge(e)
        for e in raw_edges
        if (e.get("from_id") or e.get("source")) in kept_ids
        and (e.get("to_id") or e.get("target")) in kept_ids
    ]
    return JSONResponse({"nodes": filtered_nodes, "edges": web_edges})


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


def _extract_nodes_edges(
    raw: QueryResult,
) -> tuple[dict[str, GraphNodeOut], list[GraphEdgeOut]]:
    """Extract nodes and edges from a QueryResult.

    ``raw`` is a QueryResult whose rows are ``list[list[Any]]``. Each cell
    may be a dict representing a node (has ``id`` key) or an edge (has
    ``source`` and ``target`` keys), or a scalar (ignored).

    Nodes are deduplicated by id. The federation root is filtered out.
    """
    nodes: dict[str, GraphNodeOut] = {}
    edges: list[GraphEdgeOut] = []
    for row in raw.rows:
        for cell in row:
            if not isinstance(cell, dict):
                continue
            if "source" in cell and "target" in cell and "kind" in cell:
                # Edge-shaped cell
                edges.append(
                    GraphEdgeOut(source=cell["source"], target=cell["target"], kind=cell["kind"])
                )
            elif "id" in cell:
                # Node-shaped cell
                node_id = cell["id"]
                if node_id == _FEDERATION_ID:
                    continue
                if node_id not in nodes:
                    nodes[node_id] = GraphNodeOut(
                        id=node_id,
                        label=cell.get("label", node_id),
                        kind=cell.get("kind", "unknown"),
                        kb=cell.get("kb"),
                    )
    return nodes, edges


@router.post("/query", response_model=GraphQueryResult)
async def proxy_query(body: CypherQuery, request: Request) -> GraphQueryResult:
    if _WRITE_RE.search(body.cypher):
        raise HTTPException(status_code=400, detail="writes are not permitted")
    client = _client_or_none(request)
    if client is None:
        raise HTTPException(status_code=410, detail="graph is disabled")
    try:
        result = await client.graph_query(cypher=body.cypher, params=body.params)
    except GraphUnavailable as exc:
        raise HTTPException(status_code=410, detail="graph is disabled") from exc
    nodes, edges = _extract_nodes_edges(result)
    return GraphQueryResult(nodes=list(nodes.values()), edges=edges)


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
