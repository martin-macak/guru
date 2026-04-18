"""HTTP-over-UDS client for guru-graph daemon.

Lives in guru-core so guru-server, guru-cli, and guru-mcp can share it.
Never imports the Neo4j driver — the daemon is the only code that talks
to Neo4j.

All transport failures and protocol/health errors are translated to
GraphUnavailable so consumers can use graph_or_skip to degrade silently.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx

from .graph_errors import GraphUnavailable
from .graph_types import (
    AnnotationCreate,
    AnnotationNode,
    ArtifactFindQuery,
    ArtifactLink,
    ArtifactLinkCreate,
    ArtifactLinkKind,
    ArtifactNeighborsResult,
    ArtifactNode,
    CypherQuery,
    Health,
    KbLink,
    KbLinkCreate,
    KbNode,
    KbUpsert,
    LinkKind,
    OrphanAnnotation,
    ParseResultPayload,
    QueryResult,
    ReattachRequest,
    VersionInfo,
)

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "1.1.0"
PROTOCOL_HEADER = "X-Guru-Graph-Protocol"


class GraphClient:
    """Async HTTP/UDS client. Raises GraphUnavailable on any failure to reach
    the daemon, 503, 426, timeout, or stale socket.

    Pass ``socket_path=None`` (the default) to let the client discover the
    platform-default socket path from ``guru_graph.config.GraphPaths`` at
    call time. This keeps guru-server and guru-cli free of a compile-time
    dependency on guru-graph.
    """

    _timeout = httpx.Timeout(5.0, read=30.0)

    def __init__(
        self,
        *,
        socket_path: str | None = None,
        auto_start: bool = True,
        ready_timeout_seconds: float = 30.0,
    ):
        self._socket_path = socket_path
        self.auto_start = auto_start
        self._ready_timeout = ready_timeout_seconds

    @property
    def socket_path(self) -> str:
        """Return the effective socket path, discovering it lazily if needed."""
        if self._socket_path is not None:
            return self._socket_path
        try:
            from guru_graph.config import GraphPaths  # type: ignore

            return str(GraphPaths.default().socket)
        except ImportError as e:
            raise GraphUnavailable("guru-graph is not installed") from e

    def _transport(self) -> httpx.AsyncHTTPTransport:
        return httpx.AsyncHTTPTransport(uds=self.socket_path)

    def _headers(self) -> dict[str, str]:
        return {PROTOCOL_HEADER: PROTOCOL_VERSION}

    async def _ensure_daemon(self) -> None:
        if not self.auto_start:
            return
        try:
            from guru_graph.config import GraphPaths
            from guru_graph.lifecycle import connect_or_spawn
        except ImportError:
            return
        paths = GraphPaths.default()
        if Path(self.socket_path) == paths.socket:
            await asyncio.to_thread(
                connect_or_spawn,
                paths=paths,
                ready_timeout_seconds=self._ready_timeout,
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            await self._ensure_daemon()
        except Exception as e:
            raise GraphUnavailable(f"autostart failed: {e}") from e
        merged_headers = self._headers()
        if headers:
            merged_headers.update(headers)
        try:
            async with httpx.AsyncClient(
                transport=self._transport(),
                timeout=self._timeout,
            ) as client:
                resp = await client.request(
                    method,
                    f"http://localhost{path}",
                    headers=merged_headers,
                    json=json,
                )
        except httpx.HTTPError as e:
            raise GraphUnavailable(f"transport error: {e}") from e
        except FileNotFoundError as e:
            raise GraphUnavailable(f"socket missing: {e}") from e

        if resp.status_code == 426:
            raise GraphUnavailable(f"protocol upgrade required: {resp.json()}")
        if resp.status_code == 503:
            raise GraphUnavailable(f"daemon unhealthy: {resp.text}")
        if resp.status_code >= 500:
            raise GraphUnavailable(f"daemon error {resp.status_code}: {resp.text}")
        return resp

    async def health(self) -> Health:
        resp = await self._request("GET", "/health")
        if resp.status_code != 200:
            raise GraphUnavailable(f"unexpected {resp.status_code}")
        return Health.model_validate(resp.json())

    async def version(self) -> VersionInfo:
        resp = await self._request("GET", "/version")
        return VersionInfo.model_validate(resp.json())

    async def upsert_kb(self, req: KbUpsert) -> KbNode:
        resp = await self._request("POST", "/kbs", json=req.model_dump())
        return KbNode.model_validate(resp.json())

    async def get_kb(self, name: str) -> KbNode | None:
        resp = await self._request("GET", f"/kbs/{quote(name, safe='')}")
        if resp.status_code == 404:
            return None
        return KbNode.model_validate(resp.json())

    async def list_kbs(
        self,
        *,
        prefix: str | None = None,
        tag: str | None = None,
    ) -> list[KbNode]:
        qs = []
        if prefix:
            qs.append(f"prefix={quote(prefix)}")
        if tag:
            qs.append(f"tag={quote(tag)}")
        path = "/kbs" + ("?" + "&".join(qs) if qs else "")
        resp = await self._request("GET", path)
        return [KbNode.model_validate(r) for r in resp.json()]

    async def delete_kb(self, name: str) -> bool:
        resp = await self._request("DELETE", f"/kbs/{quote(name, safe='')}")
        return resp.status_code == 204

    async def link_kbs(
        self,
        *,
        from_kb: str,
        to_kb: str,
        kind: LinkKind,
        metadata: dict | None = None,
    ) -> KbLink:
        body = KbLinkCreate(to_kb=to_kb, kind=kind, metadata=metadata or {})
        resp = await self._request(
            "POST",
            f"/kbs/{quote(from_kb, safe='')}/links",
            json=body.model_dump(mode="json"),
        )
        return KbLink.model_validate(resp.json())

    async def unlink_kbs(
        self,
        *,
        from_kb: str,
        to_kb: str,
        kind: LinkKind,
    ) -> bool:
        resp = await self._request(
            "DELETE",
            f"/kbs/{quote(from_kb, safe='')}/links/{quote(to_kb, safe='')}/{kind.value}",
        )
        return resp.status_code == 204

    async def list_links(
        self,
        *,
        name: str,
        direction: Literal["in", "out", "both"] = "both",
    ) -> list[KbLink]:
        resp = await self._request(
            "GET",
            f"/kbs/{quote(name, safe='')}/links?direction={direction}",
        )
        return [KbLink.model_validate(r) for r in resp.json()]

    async def submit_parse_result(self, *, kb_name: str, payload: ParseResultPayload) -> None:
        """Submit a ParseResultPayload to the graph daemon's ingest endpoint.

        Raises :class:`GraphUnavailable` on any transport, protocol, or
        daemon-side error. A successful submission returns nothing; the graph
        is reconciled in-place.
        """
        resp = await self._request(
            "POST",
            f"/ingest/parse-result?kb_name={quote(kb_name, safe='')}",
            json=payload.model_dump(mode="json"),
        )
        if resp.status_code != 204:
            raise GraphUnavailable(
                f"unexpected status from /ingest/parse-result: {resp.status_code}"
            )

    async def delete_document_in_graph(self, *, kb_name: str, doc_id: str) -> None:
        """Remove a Document and its CONTAINS subtree from the graph.

        Raises :class:`GraphUnavailable` on any error. Safe to call for a
        document that doesn't exist in the graph (204 is returned either way).
        """
        resp = await self._request(
            "DELETE",
            f"/ingest/documents/{quote(doc_id, safe='')}?kb_name={quote(kb_name, safe='')}",
        )
        if resp.status_code != 204:
            raise GraphUnavailable(
                f"unexpected status from /ingest/documents/{doc_id}: {resp.status_code}"
            )

    async def create_link(self, req: ArtifactLinkCreate, *, author: str) -> ArtifactLink:
        """Create a directed relationship between two artifacts.

        Returns the resulting :class:`ArtifactLink`. Raises
        :class:`GraphUnavailable` on any transport, protocol, or daemon-side
        error, including 404 (unknown artifact) or 422 (bad payload).
        """
        resp = await self._request(
            "POST",
            "/relates",
            json=req.model_dump(mode="json"),
            headers={"X-Guru-Author": author},
        )
        if resp.status_code != 201:
            raise GraphUnavailable(f"unexpected status from POST /relates: {resp.status_code}")
        return ArtifactLink.model_validate(resp.json())

    async def delete_link(self, *, from_id: str, to_id: str, kind: ArtifactLinkKind) -> bool:
        """Delete a directed relationship between two artifacts.

        Returns ``True`` if the link was deleted (204), ``False`` if it was not
        found (404). Raises :class:`GraphUnavailable` on any other status or
        transport error.
        """
        resp = await self._request(
            "DELETE",
            "/relates",
            json={"from_id": from_id, "to_id": to_id, "kind": kind.value},
        )
        if resp.status_code == 204:
            return True
        if resp.status_code == 404:
            return False
        raise GraphUnavailable(f"unexpected status from DELETE /relates: {resp.status_code}")

    async def describe_artifact(self, *, node_id: str) -> ArtifactNode | None:
        """Fetch an Artifact by id with its annotations + RELATES links inline.

        Returns None if no node with `node_id` exists. Raises GraphUnavailable
        on transport, protocol, or daemon errors.
        """
        resp = await self._request("GET", f"/artifacts/{quote(node_id, safe='')}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise GraphUnavailable(
                f"unexpected status from GET /artifacts/{node_id}: {resp.status_code}"
            )
        return ArtifactNode.model_validate(resp.json())

    async def neighbors(
        self,
        *,
        node_id: str,
        direction: Literal["in", "out", "both"] = "both",
        rel_type: Literal["CONTAINS", "RELATES", "both"] = "both",
        kind: str | None = None,
        depth: int = 1,
        limit: int = 50,
    ) -> ArtifactNeighborsResult:
        """Walk neighbors of `node_id` up to `depth` hops, filtered by direction/rel_type/kind."""
        qs = f"?direction={direction}&rel_type={rel_type}&depth={depth}&limit={limit}"
        if kind:
            qs += f"&kind={quote(kind, safe='')}"
        resp = await self._request("GET", f"/artifacts/{quote(node_id, safe='')}/neighbors{qs}")
        if resp.status_code != 200:
            raise GraphUnavailable(
                f"unexpected status from GET /artifacts/{node_id}/neighbors: {resp.status_code}"
            )
        return ArtifactNeighborsResult.model_validate(resp.json())

    async def find_artifacts(self, q: ArtifactFindQuery) -> list[ArtifactNode]:
        """Search for artifacts matching the given filters. Empty list if none."""
        resp = await self._request("POST", "/artifacts/find", json=q.model_dump(exclude_none=True))
        if resp.status_code != 200:
            raise GraphUnavailable(
                f"unexpected status from POST /artifacts/find: {resp.status_code}"
            )
        return [ArtifactNode.model_validate(r) for r in resp.json()]

    async def graph_query(self, *, cypher: str, params: dict | None = None) -> QueryResult:
        """Read-only Cypher query — forces read_only=True regardless of caller intent."""
        return await self.query(cypher=cypher, params=params, read_only=True)

    async def create_annotation(self, req: AnnotationCreate, *, author: str) -> AnnotationNode:
        """Create an annotation. Returns the resulting AnnotationNode.

        SUMMARY kind replaces the existing summary for the target (idempotent);
        other kinds append. Raises :class:`GraphUnavailable` on transport or
        daemon errors, including 404 when the target doesn't exist.
        """
        resp = await self._request(
            "POST",
            "/annotations",
            json=req.model_dump(mode="json"),
            headers={"X-Guru-Author": author},
        )
        if resp.status_code != 201:
            raise GraphUnavailable(f"unexpected status from POST /annotations: {resp.status_code}")
        return AnnotationNode.model_validate(resp.json())

    async def delete_annotation(self, *, annotation_id: str) -> bool:
        """Delete an annotation by id. Returns True on success, False if not found."""
        resp = await self._request(
            "DELETE",
            f"/annotations/{quote(annotation_id, safe='')}",
        )
        if resp.status_code == 204:
            return True
        if resp.status_code == 404:
            return False
        raise GraphUnavailable(
            f"unexpected status from DELETE /annotations/{annotation_id}: {resp.status_code}"
        )

    async def list_orphans(self, *, limit: int = 50) -> list[OrphanAnnotation]:
        """List orphaned annotations (those whose target node was deleted)."""
        resp = await self._request("GET", f"/annotations/orphans?limit={limit}")
        if resp.status_code != 200:
            raise GraphUnavailable(
                f"unexpected status from GET /annotations/orphans: {resp.status_code}"
            )
        return [OrphanAnnotation.model_validate(r) for r in resp.json()]

    async def reattach_orphan(self, *, annotation_id: str, new_node_id: str) -> AnnotationNode:
        """Reattach an orphaned annotation to a new target node."""
        resp = await self._request(
            "POST",
            f"/annotations/{quote(annotation_id, safe='')}/reattach",
            json=ReattachRequest(new_node_id=new_node_id).model_dump(mode="json"),
        )
        if resp.status_code != 200:
            raise GraphUnavailable(
                f"unexpected status from POST /annotations/{annotation_id}/reattach: {resp.status_code}"
            )
        return AnnotationNode.model_validate(resp.json())

    async def query(
        self,
        *,
        cypher: str,
        params: dict | None = None,
        read_only: bool = True,
    ) -> QueryResult:
        q = CypherQuery(cypher=cypher, params=params or {}, read_only=read_only)
        resp = await self._request("POST", "/query", json=q.model_dump())
        return QueryResult.model_validate(resp.json())
