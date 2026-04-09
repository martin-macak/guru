from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from guru_core.autostart import ensure_server
from guru_core.client import GuruClient
from guru_core.discovery import find_guru_root

mcp = FastMCP("guru")


def _get_client() -> GuruClient:
    """Discover project root and return a configured client."""
    guru_root = find_guru_root(Path.cwd())
    ensure_server(guru_root)
    return GuruClient(guru_root=guru_root)


@mcp.tool()
async def search(query: str, n_results: int = 10, filters: dict | None = None) -> list:
    """Semantic search over the knowledge base.

    Args:
        query: Natural language search query.
        n_results: Maximum number of results to return (default 10).
        filters: Optional metadata filters as key-value pairs.
    """
    client = _get_client()
    return await client.search(query, n_results, filters)


@mcp.tool()
async def get_document(file_path: str) -> dict:
    """Retrieve a full document with its metadata.

    Args:
        file_path: Path to the document relative to project root.
    """
    client = _get_client()
    return await client.get_document(file_path)


@mcp.tool()
async def list_documents(filters: dict | None = None) -> list:
    """Browse the document catalog with optional metadata filters.

    Args:
        filters: Optional metadata filters as key-value pairs.
    """
    client = _get_client()
    return await client.list_documents(filters)


@mcp.tool()
async def get_section(file_path: str, header_path: str) -> dict:
    """Retrieve a specific section of a document by header breadcrumb.

    Args:
        file_path: Path to the document relative to project root.
        header_path: Header breadcrumb path (e.g. "Auth > OAuth > Token Refresh").
    """
    client = _get_client()
    return await client.get_section(file_path, header_path)


@mcp.tool()
async def index_status() -> dict:
    """Get the current index status including health, document count, and staleness."""
    client = _get_client()
    return await client.status()


def main():
    mcp.run()
