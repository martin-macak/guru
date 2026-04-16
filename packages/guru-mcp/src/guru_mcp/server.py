from __future__ import annotations

import json
from pathlib import Path

from fastmcp import FastMCP

from guru_core.autostart import ensure_server
from guru_core.client import GuruClient
from guru_core.config import federation_dir, resolve_config
from guru_core.discovery import find_guru_root
from guru_mcp.federation import CodebaseCloner, FederatedSearcher
from guru_server.federation import FederationRegistry

mcp = FastMCP("guru")


def _get_client() -> GuruClient:
    """Discover project root and return a configured client."""
    guru_root = find_guru_root(Path.cwd())
    ensure_server(guru_root)
    return GuruClient(guru_root=guru_root)


def _get_registry() -> FederationRegistry | None:
    """Get federation registry for the current project, or None if unavailable."""
    try:
        guru_root = find_guru_root(Path.cwd())
        config = resolve_config(project_root=guru_root)
        name = config.name or guru_root.name
        socket_path = str(guru_root / ".guru" / "guru.sock")
        return FederationRegistry(
            name=name,
            pid=0,  # Not used for reads
            socket_path=socket_path,
            project_root=str(guru_root),
            federation_dir=federation_dir(),
        )
    except Exception:
        return None


def _is_pid_alive(pid: int) -> bool:
    import os

    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


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
async def get_document(file_path: str, server_name: str | None = None) -> dict:
    """Retrieve a full document with its metadata.

    Args:
        file_path: Path to the document relative to project root.
        server_name: Optional peer name. If set, retrieves from that peer instead of locally.
    """
    if server_name is not None:
        registry = _get_registry()
        if registry is None:
            return {"error": "Federation not available"}
        peers = registry.list_peers()
        peer = next((p for p in peers if p["name"] == server_name), None)
        if peer is None:
            return {"error": f"Peer '{server_name}' not found"}
        client = GuruClient.from_socket(peer["socket"])
    else:
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
async def get_section(file_path: str, header_path: str, server_name: str | None = None) -> dict:
    """Retrieve a specific section of a document by header breadcrumb.

    Args:
        file_path: Path to the document relative to project root.
        header_path: Header breadcrumb path (e.g. "Auth > OAuth > Token Refresh").
        server_name: Optional peer name. If set, retrieves from that peer instead of locally.
    """
    if server_name is not None:
        registry = _get_registry()
        if registry is None:
            return {"error": "Federation not available"}
        peers = registry.list_peers()
        peer = next((p for p in peers if p["name"] == server_name), None)
        if peer is None:
            return {"error": f"Peer '{server_name}' not found"}
        client = GuruClient.from_socket(peer["socket"])
    else:
        client = _get_client()
    return await client.get_section(file_path, header_path)


@mcp.tool()
async def index_status() -> dict:
    """Get the current index status including health, document count, and staleness."""
    client = _get_client()
    return await client.status()


@mcp.tool()
async def federated_search(
    query: str,
    n_results: int = 10,
    filters: dict | None = None,
    group_by_server: bool = True,
) -> dict:
    """Search across local knowledge base and all discovered federation peers.

    Results from each peer are collected in parallel with a timeout.
    Unreachable peers are reported but do not cause failure.

    Args:
        query: Natural language search query.
        n_results: Maximum results per server (default 10).
        filters: Optional metadata filters as key-value pairs.
        group_by_server: If True (default), results grouped by server name.
            If False, results merged into a single list sorted by score.
    """
    client = _get_client()
    registry = _get_registry()
    peers = registry.list_peers() if registry else []
    local_name = registry.name if registry else "local"
    searcher = FederatedSearcher(
        local_client=client,
        local_name=local_name,
        peers=peers,
    )
    return await searcher.search(query, n_results, filters, group_by_server)


@mcp.tool()
async def list_peers() -> dict:
    """List all discovered federation peers with their status.

    Returns peers with name, project_root, and status (alive/unreachable).
    The current server is excluded from the list.
    """
    registry = _get_registry()
    if registry is None:
        return {"peers": []}

    peers = []
    for path in registry.federation_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("name") == registry.name:
            continue
        pid = data.get("pid")
        alive = pid is not None and _is_pid_alive(pid)
        peers.append(
            {
                "name": data.get("name", path.stem),
                "project_root": data.get("project_root", ""),
                "status": "alive" if alive else "unreachable",
            }
        )
    return {"peers": peers}


@mcp.tool()
async def clone_codebase(server_name: str) -> dict:
    """Clone a federation peer's codebase locally for exploration.

    Copies the peer's project files (respecting .gitignore) to
    .guru/federated/<server_name>/. Returns the local path.
    Use unmount_codebase to clean up when done.

    Args:
        server_name: Name of the peer to clone.
    """
    registry = _get_registry()
    if registry is None:
        return {"error": "Federation not available"}
    peers = registry.list_peers()
    peer = next((p for p in peers if p["name"] == server_name), None)
    if peer is None:
        return {"error": f"Peer '{server_name}' not found"}
    guru_root = find_guru_root(Path.cwd())
    cloner = CodebaseCloner(local_project_root=guru_root)
    try:
        path = cloner.clone(server_name, peer["project_root"])
        return {"path": path, "server_name": server_name}
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Clone failed: {exc}"}


@mcp.tool()
async def unmount_codebase(server_name: str) -> dict:
    """Remove a previously cloned peer codebase.

    Idempotent — succeeds even if no clone exists.

    Args:
        server_name: Name of the peer whose clone to remove.
    """
    guru_root = find_guru_root(Path.cwd())
    cloner = CodebaseCloner(local_project_root=guru_root)
    cloner.unmount(server_name)
    return {"status": "ok", "server_name": server_name}


def main():
    mcp.run()
