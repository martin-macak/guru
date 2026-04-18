from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

from guru_core.autostart import ensure_server
from guru_core.client import GuruClient
from guru_core.config import federation_dir, resolve_config
from guru_core.discovery import find_guru_root
from guru_mcp.federation import CodebaseCloner, FederatedSearcher
from guru_server.federation import FederationRegistry

mcp = FastMCP("guru")

# Identifier sent to guru-server on graph writes via the ``x-guru-mcp-client``
# header. The server stamps annotations/links with ``agent:<this-value>`` when
# no explicit ``X-Guru-Author`` header is present. Held as a constant for now;
# future work could detect the actual client (Claude Code, Cursor, VSCode, ...).
_MCP_CLIENT_NAME = "claude-code"


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


# --- Graph tools (proxy to guru-server /graph/* via GuruClient) ---


@mcp.tool()
async def graph_describe(node_id: str) -> dict:
    """Fetch a graph node with its properties, annotations, and direct links.

    Returns ``{"status": "graph_disabled", ...}`` if the graph daemon isn't
    reachable (the server swallows ``GraphUnavailable`` and falls back).

    Args:
        node_id: Stable graph node id (e.g. ``kb::doc::path/to/file.md``).
    """
    client = _get_client()
    return await client.graph_describe(node_id=node_id)


@mcp.tool()
async def graph_neighbors(
    node_id: str,
    direction: Literal["in", "out", "both"] = "both",
    rel_type: Literal["CONTAINS", "RELATES", "both"] = "both",
    kind: str | None = None,
    depth: int = 1,
    limit: int = 50,
) -> dict:
    """Walk neighbors of ``node_id`` up to ``depth`` hops.

    Args:
        node_id: Source node id.
        direction: ``in``, ``out``, or ``both`` (default ``both``).
        rel_type: ``CONTAINS``, ``RELATES``, or ``both`` (default ``both``).
        kind: Optional RELATES sub-kind filter (imports, calls, ...).
        depth: Hop count (default 1).
        limit: Max neighbors to return (default 50).
    """
    client = _get_client()
    return await client.graph_neighbors(
        node_id=node_id,
        direction=direction,
        rel_type=rel_type,
        kind=kind,
        depth=depth,
        limit=limit,
    )


@mcp.tool()
async def graph_find(
    name: str | None = None,
    qualname_prefix: str | None = None,
    label: str | None = None,
    tag: str | None = None,
    kb_name: str | None = None,
    limit: int = 50,
) -> dict:
    """Search artifacts by name, qualname prefix, label, tag, or KB name.

    Only non-None arguments are forwarded to the server, so omitting a
    filter doesn't constrain the search.

    Args:
        name: Exact node name (e.g. function/class name).
        qualname_prefix: Match nodes whose qualname starts with this prefix.
        label: Filter by node label (e.g. ``Function``, ``Document``).
        tag: Filter by annotation tag.
        kb_name: Restrict to a single knowledge-base by name.
        limit: Max results (default 50).
    """
    client = _get_client()
    body: dict = {"limit": limit}
    if name is not None:
        body["name"] = name
    if qualname_prefix is not None:
        body["qualname_prefix"] = qualname_prefix
    if label is not None:
        body["label"] = label
    if tag is not None:
        body["tag"] = tag
    if kb_name is not None:
        body["kb_name"] = kb_name
    return await client.graph_find(body=body)


@mcp.tool()
async def graph_annotate(
    node_id: str,
    kind: Literal["summary", "gotcha", "caveat", "note"],
    body: str,
    tags: list[str] | None = None,
) -> dict:
    """Create or replace an annotation on a graph node.

    ``summary`` annotations replace the existing summary in-place; the other
    kinds append. The MCP server stamps ``agent:claude-code`` as author.

    Args:
        node_id: Target node id.
        kind: ``summary``, ``gotcha``, ``caveat``, or ``note``.
        body: Annotation text.
        tags: Optional list of tags to attach.
    """
    client = _get_client()
    payload = {"node_id": node_id, "kind": kind, "body": body, "tags": tags or []}
    return await client.graph_create_annotation(body=payload, mcp_client=_MCP_CLIENT_NAME)


@mcp.tool()
async def graph_delete_annotation(annotation_id: str) -> dict:
    """Delete an annotation by its id.

    Args:
        annotation_id: The annotation's stable id.
    """
    client = _get_client()
    return await client.graph_delete_annotation(annotation_id=annotation_id)


@mcp.tool()
async def graph_link(
    from_id: str,
    to_id: str,
    kind: Literal["imports", "inherits_from", "implements", "calls", "references", "documents"],
    metadata: dict | None = None,
) -> dict:
    """Create a typed RELATES link between two artifacts.

    The MCP server stamps ``agent:claude-code`` as author.

    Args:
        from_id: Source node id.
        to_id: Target node id.
        kind: Link sub-kind (imports, inherits_from, implements, calls,
            references, or documents).
        metadata: Optional metadata dict to attach to the link.
    """
    client = _get_client()
    payload = {
        "from_id": from_id,
        "to_id": to_id,
        "kind": kind,
        "metadata": metadata or {},
    }
    return await client.graph_create_link(body=payload, mcp_client=_MCP_CLIENT_NAME)


@mcp.tool()
async def graph_unlink(from_id: str, to_id: str, kind: str) -> dict:
    """Delete a typed RELATES link between two artifacts.

    Args:
        from_id: Source node id.
        to_id: Target node id.
        kind: Link sub-kind to delete.
    """
    client = _get_client()
    payload = {"from_id": from_id, "to_id": to_id, "kind": kind}
    return await client.graph_delete_link(body=payload)


@mcp.tool()
async def graph_orphans(limit: int = 50) -> dict:
    """List orphaned annotations whose target node was deleted.

    Args:
        limit: Max results (default 50).
    """
    client = _get_client()
    return await client.graph_orphans(limit=limit)


@mcp.tool()
async def graph_reattach_orphan(annotation_id: str, new_node_id: str) -> dict:
    """Reattach an orphaned annotation to a new target node.

    Args:
        annotation_id: The orphaned annotation's id.
        new_node_id: New target node id.
    """
    client = _get_client()
    payload = {"new_node_id": new_node_id}
    return await client.graph_reattach_orphan(annotation_id=annotation_id, body=payload)


@mcp.tool()
async def graph_query(cypher: str, params: dict | None = None) -> dict:
    """Run a read-only Cypher query against the graph.

    Writes are blocked at the server (``read_only: True`` is enforced
    server-side regardless of what the client sends).

    Args:
        cypher: Cypher query string.
        params: Optional query parameters dict.
    """
    client = _get_client()
    return await client.graph_query(cypher=cypher, params=params)


def main():
    mcp.run()
