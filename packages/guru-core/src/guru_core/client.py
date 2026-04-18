from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

logger = logging.getLogger(__name__)


class GuruClient:
    """Async HTTP client for the guru-server REST API over Unix domain socket."""

    # Server is local (UDS) so connection should be fast, but server-side
    # processing (e.g. Ollama embeddings during indexing) can take minutes.
    _timeout = httpx.Timeout(5.0, read=None)

    def __init__(self, guru_root: Path):
        self.guru_root = guru_root
        self.socket_path = str(guru_root / ".guru" / "guru.sock")

    @classmethod
    def from_socket(cls, socket_path: str) -> GuruClient:
        """Create a client that connects to an arbitrary socket path.

        Used for federation — connecting to a peer's socket without
        knowing its guru_root.
        """
        instance = cls.__new__(cls)
        instance.guru_root = None
        instance.socket_path = socket_path
        return instance

    def _transport(self) -> httpx.AsyncHTTPTransport:
        return httpx.AsyncHTTPTransport(uds=self.socket_path)

    async def _get(self, path: str, headers: dict[str, str] | None = None) -> dict | list:
        async with httpx.AsyncClient(transport=self._transport(), timeout=self._timeout) as client:
            logger.debug("GET %s", path)
            resp = await client.get(f"http://localhost{path}", headers=headers)
            logger.debug("GET %s -> %d", path, resp.status_code)
            if resp.is_error:
                resp.raise_for_status()
            return resp.json()

    async def _post(
        self, path: str, json: dict, headers: dict[str, str] | None = None
    ) -> dict | list:
        async with httpx.AsyncClient(transport=self._transport(), timeout=self._timeout) as client:
            logger.debug("POST %s", path)
            resp = await client.post(f"http://localhost{path}", json=json, headers=headers)
            logger.debug("POST %s -> %d", path, resp.status_code)
            if resp.is_error:
                resp.raise_for_status()
            return resp.json()

    async def _delete(self, path: str, headers: dict[str, str] | None = None) -> dict | list:
        async with httpx.AsyncClient(transport=self._transport(), timeout=self._timeout) as client:
            logger.debug("DELETE %s", path)
            resp = await client.delete(f"http://localhost{path}", headers=headers)
            logger.debug("DELETE %s -> %d", path, resp.status_code)
            if resp.is_error:
                resp.raise_for_status()
            return resp.json()

    async def _request_with_body(
        self,
        method: str,
        path: str,
        body: dict,
        headers: dict[str, str] | None = None,
    ) -> dict | list:
        """Issue an arbitrary HTTP request with a JSON body.

        Needed because httpx's ``client.delete()`` does not accept ``json=`` —
        DELETE-with-body must go through the generic ``request()`` API.
        """
        async with httpx.AsyncClient(transport=self._transport(), timeout=self._timeout) as client:
            logger.debug("%s %s", method, path)
            resp = await client.request(
                method, f"http://localhost{path}", json=body, headers=headers
            )
            logger.debug("%s %s -> %d", method, path, resp.status_code)
            if resp.is_error:
                resp.raise_for_status()
            return resp.json()

    async def status(self) -> dict:
        return await self._get("/status")

    async def search(self, query: str, n_results: int = 10, filters: dict | None = None) -> list:
        return await self._post(
            "/search",
            {
                "query": query,
                "n_results": n_results,
                "filters": filters or {},
            },
        )

    async def list_documents(self, filters: dict | None = None) -> list:
        path = "/documents"
        if filters:
            path = f"{path}?{urlencode(filters)}"
        return await self._get(path)

    async def get_document(self, file_path: str) -> dict:
        # Preserve slashes (path separators) but encode other special chars
        encoded = quote(file_path, safe="/")
        return await self._get(f"/documents/{encoded}")

    async def get_section(self, file_path: str, header_path: str) -> dict:
        encoded_fp = quote(file_path, safe="/")
        encoded_hp = quote(header_path, safe="")
        return await self._get(f"/documents/{encoded_fp}/sections/{encoded_hp}")

    async def trigger_index(self) -> dict:
        return await self._post("/index", {})

    async def get_job(self, job_id: str) -> dict:
        return await self._get(f"/jobs/{job_id}")

    async def cache_info(self) -> dict:
        return await self._get("/cache")

    async def cache_clear(self, model: str | None = None) -> dict:
        path = "/cache"
        if model:
            path = f"{path}?{urlencode({'model': model})}"
        return await self._delete(path)

    async def cache_prune(self, older_than_ms: int) -> dict:
        return await self._post("/cache/prune", {"older_than_ms": older_than_ms})

    # --- Graph proxy methods (call /graph/* on guru-server) ---

    async def graph_describe(self, *, node_id: str) -> dict:
        encoded = quote(node_id, safe="")
        return await self._get(f"/graph/describe/{encoded}")

    async def graph_neighbors(
        self,
        *,
        node_id: str,
        direction: str = "both",
        rel_type: str = "both",
        kind: str | None = None,
        depth: int = 1,
        limit: int = 50,
    ) -> dict:
        encoded = quote(node_id, safe="")
        qs: dict[str, str | int] = {
            "direction": direction,
            "rel_type": rel_type,
            "depth": depth,
            "limit": limit,
        }
        if kind is not None:
            qs["kind"] = kind
        return await self._get(f"/graph/neighbors/{encoded}?{urlencode(qs)}")

    async def graph_find(self, *, body: dict) -> dict | list:
        return await self._post("/graph/find", body)

    async def graph_create_annotation(self, *, body: dict, mcp_client: str | None) -> dict:
        headers = {"x-guru-mcp-client": mcp_client} if mcp_client else None
        return await self._post("/graph/annotations", body, headers=headers)

    async def graph_delete_annotation(self, *, annotation_id: str) -> dict:
        return await self._delete(f"/graph/annotations/{quote(annotation_id, safe='')}")

    async def graph_create_link(self, *, body: dict, mcp_client: str | None) -> dict:
        headers = {"x-guru-mcp-client": mcp_client} if mcp_client else None
        return await self._post("/graph/links", body, headers=headers)

    async def graph_delete_link(self, *, body: dict) -> dict:
        return await self._request_with_body("DELETE", "/graph/links", body)

    async def graph_orphans(self, *, limit: int = 50) -> dict | list:
        return await self._get(f"/graph/orphans?limit={limit}")

    async def graph_reattach_orphan(self, *, annotation_id: str, body: dict) -> dict:
        return await self._post(f"/graph/orphans/{quote(annotation_id, safe='')}/reattach", body)

    async def graph_query(self, *, cypher: str, params: dict | None = None) -> dict:
        return await self._post(
            "/graph/query",
            {"cypher": cypher, "params": params or {}, "read_only": True},
        )
