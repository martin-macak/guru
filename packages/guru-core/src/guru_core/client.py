from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlencode

import httpx


class GuruClient:
    """Async HTTP client for the guru-server REST API over Unix domain socket."""

    def __init__(self, guru_root: Path):
        self.guru_root = guru_root
        self.socket_path = str(guru_root / ".guru" / "guru.sock")

    def _transport(self) -> httpx.AsyncHTTPTransport:
        return httpx.AsyncHTTPTransport(uds=self.socket_path)

    async def _get(self, path: str) -> dict | list:
        async with httpx.AsyncClient(transport=self._transport()) as client:
            resp = await client.get(f"http://localhost{path}")
            if resp.is_error:
                resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict) -> dict | list:
        async with httpx.AsyncClient(transport=self._transport()) as client:
            resp = await client.post(f"http://localhost{path}", json=json)
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

    async def trigger_index(self, path: str | None = None) -> dict:
        return await self._post("/index", {"path": path})
