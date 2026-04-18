"""Tests for the 10 graph_* MCP tools added in PR-5 / Task 5.4.

The MCP tool layer is a thin wrapper around ``GuruClient`` graph methods.
Each test patches ``guru_mcp.server._get_client`` and asserts the right
client method was invoked with the right kwargs / payload.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from guru_mcp import server

# --- registry / safety tests ---------------------------------------------------


def test_all_10_graph_tools_registered():
    """All 10 tools from Task 5.4 must be exposed on the MCP server."""
    tools = asyncio.run(server.mcp.list_tools())
    tool_names = {t.name for t in tools}
    expected = {
        "graph_describe",
        "graph_neighbors",
        "graph_find",
        "graph_annotate",
        "graph_delete_annotation",
        "graph_link",
        "graph_unlink",
        "graph_orphans",
        "graph_reattach_orphan",
        "graph_query",
    }
    missing = expected - tool_names
    assert not missing, f"missing graph tools: {missing}"


def test_list_returning_tools_advertise_list_in_signature():
    """graph_find and graph_orphans return lists from the underlying server.

    FastMCP's structured_content layer raises ToolError if a tool annotated
    ``-> dict`` returns a list. So both must declare ``list | dict`` (or
    ``list``) so FastMCP wraps the result correctly.
    """
    import inspect

    for name in ("graph_find", "graph_orphans"):
        sig = inspect.signature(getattr(server, name))
        ret = str(sig.return_annotation)
        assert "list" in ret, (
            f"{name} returns a list at runtime; signature must declare 'list' "
            f"so FastMCP wraps correctly. Got: {ret}"
        )


def test_no_write_tools_for_kb_crud():
    """The 10 graph tools deliberately exclude KB-CRUD writes (which exist in
    guru-cli but never the MCP surface — agents cannot edit federation state)."""
    tools = asyncio.run(server.mcp.list_tools())
    tool_names = {t.name for t in tools}
    forbidden = {"upsert_kb", "delete_kb", "link_kbs", "unlink_kbs"}
    leaked = tool_names & forbidden
    assert leaked == set(), f"forbidden tools present: {leaked}"


# --- per-tool tests ------------------------------------------------------------


async def test_graph_describe_calls_client():
    mock_client = MagicMock()
    mock_client.graph_describe = AsyncMock(return_value={"id": "kb::x", "label": "Document"})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_describe(node_id="kb::x")
    assert result == {"id": "kb::x", "label": "Document"}
    mock_client.graph_describe.assert_called_once_with(node_id="kb::x")


async def test_graph_neighbors_calls_client():
    mock_client = MagicMock()
    mock_client.graph_neighbors = AsyncMock(return_value={"nodes": [], "edges": []})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_neighbors(
            node_id="kb::y",
            direction="out",
            rel_type="RELATES",
            kind="imports",
            depth=2,
            limit=25,
        )
    assert result == {"nodes": [], "edges": []}
    mock_client.graph_neighbors.assert_called_once_with(
        node_id="kb::y",
        direction="out",
        rel_type="RELATES",
        kind="imports",
        depth=2,
        limit=25,
    )


async def test_graph_neighbors_defaults():
    mock_client = MagicMock()
    mock_client.graph_neighbors = AsyncMock(return_value={})
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_neighbors(node_id="kb::z")
    mock_client.graph_neighbors.assert_called_once_with(
        node_id="kb::z",
        direction="both",
        rel_type="both",
        kind=None,
        depth=1,
        limit=50,
    )


async def test_graph_find_omits_none_kwargs():
    """None-valued filters must NOT appear in the body sent to the client."""
    mock_client = MagicMock()
    mock_client.graph_find = AsyncMock(return_value=[])
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_find(name="X")
    mock_client.graph_find.assert_called_once_with(body={"name": "X", "limit": 50})


async def test_graph_find_forwards_all_filters():
    mock_client = MagicMock()
    mock_client.graph_find = AsyncMock(return_value=[])
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_find(
            name="X",
            qualname_prefix="pkg.mod.",
            label="Function",
            tag="hot",
            kb_name="my-kb",
            limit=10,
        )
    mock_client.graph_find.assert_called_once_with(
        body={
            "limit": 10,
            "name": "X",
            "qualname_prefix": "pkg.mod.",
            "label": "Function",
            "tag": "hot",
            "kb_name": "my-kb",
        }
    )


async def test_graph_annotate_passes_mcp_client_header():
    mock_client = MagicMock()
    mock_client.graph_create_annotation = AsyncMock(return_value={"id": "ann1"})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_annotate(
            node_id="kb::n",
            kind="summary",
            body="hello",
            tags=["t1", "t2"],
        )
    assert result == {"id": "ann1"}
    mock_client.graph_create_annotation.assert_called_once_with(
        body={
            "node_id": "kb::n",
            "kind": "summary",
            "body": "hello",
            "tags": ["t1", "t2"],
        },
        mcp_client="claude-code",
    )


async def test_graph_annotate_defaults_tags_to_empty_list():
    mock_client = MagicMock()
    mock_client.graph_create_annotation = AsyncMock(return_value={})
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_annotate(node_id="kb::n", kind="note", body="x")
    args = mock_client.graph_create_annotation.call_args
    assert args.kwargs["body"]["tags"] == []
    assert args.kwargs["mcp_client"] == "claude-code"


async def test_graph_delete_annotation_calls_client():
    mock_client = MagicMock()
    mock_client.graph_delete_annotation = AsyncMock(return_value={"status": "ok"})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_delete_annotation(annotation_id="ann1")
    assert result == {"status": "ok"}
    mock_client.graph_delete_annotation.assert_called_once_with(
        annotation_id="ann1", mcp_client="claude-code"
    )


async def test_graph_delete_annotation_passes_mcp_client_header():
    """Deletes are writes — must stamp ``x-guru-mcp-client`` for author tracking."""
    mock_client = MagicMock()
    mock_client.graph_delete_annotation = AsyncMock(return_value={"status": "ok"})
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_delete_annotation(annotation_id="ann1")
    args = mock_client.graph_delete_annotation.call_args
    assert args.kwargs["mcp_client"] == "claude-code"


async def test_graph_link_passes_mcp_client_header():
    mock_client = MagicMock()
    mock_client.graph_create_link = AsyncMock(return_value={"id": "lnk1"})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_link(
            from_id="kb::a",
            to_id="kb::b",
            kind="calls",
            metadata={"weight": 1},
        )
    assert result == {"id": "lnk1"}
    mock_client.graph_create_link.assert_called_once_with(
        body={
            "from_id": "kb::a",
            "to_id": "kb::b",
            "kind": "calls",
            "metadata": {"weight": 1},
        },
        mcp_client="claude-code",
    )


async def test_graph_link_defaults_metadata_to_empty_dict():
    mock_client = MagicMock()
    mock_client.graph_create_link = AsyncMock(return_value={})
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_link(from_id="a", to_id="b", kind="references")
    args = mock_client.graph_create_link.call_args
    assert args.kwargs["body"]["metadata"] == {}
    assert args.kwargs["mcp_client"] == "claude-code"


async def test_graph_unlink_calls_client():
    mock_client = MagicMock()
    mock_client.graph_delete_link = AsyncMock(return_value={"status": "ok"})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_unlink(from_id="a", to_id="b", kind="calls")
    assert result == {"status": "ok"}
    mock_client.graph_delete_link.assert_called_once_with(
        body={"from_id": "a", "to_id": "b", "kind": "calls"},
        mcp_client="claude-code",
    )


async def test_graph_unlink_passes_mcp_client_header():
    """Deletes are writes — must stamp ``x-guru-mcp-client`` for author tracking."""
    mock_client = MagicMock()
    mock_client.graph_delete_link = AsyncMock(return_value={"status": "ok"})
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_unlink(from_id="a", to_id="b", kind="references")
    args = mock_client.graph_delete_link.call_args
    assert args.kwargs["mcp_client"] == "claude-code"


async def test_graph_orphans_calls_client():
    mock_client = MagicMock()
    mock_client.graph_orphans = AsyncMock(return_value=[])
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_orphans(limit=12)
    assert result == []
    mock_client.graph_orphans.assert_called_once_with(limit=12)


async def test_graph_orphans_default_limit():
    mock_client = MagicMock()
    mock_client.graph_orphans = AsyncMock(return_value=[])
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_orphans()
    mock_client.graph_orphans.assert_called_once_with(limit=50)


async def test_graph_reattach_orphan_calls_client():
    mock_client = MagicMock()
    mock_client.graph_reattach_orphan = AsyncMock(return_value={"status": "ok"})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_reattach_orphan(annotation_id="ann1", new_node_id="kb::new")
    assert result == {"status": "ok"}
    mock_client.graph_reattach_orphan.assert_called_once_with(
        annotation_id="ann1", body={"new_node_id": "kb::new"}
    )


async def test_graph_query_forwards_cypher_and_params():
    mock_client = MagicMock()
    mock_client.graph_query = AsyncMock(return_value={"rows": []})
    with patch.object(server, "_get_client", return_value=mock_client):
        result = await server.graph_query(
            cypher="MATCH (n) RETURN n LIMIT $k",
            params={"k": 5},
        )
    assert result == {"rows": []}
    mock_client.graph_query.assert_called_once_with(
        cypher="MATCH (n) RETURN n LIMIT $k", params={"k": 5}
    )


async def test_graph_query_default_params_none():
    mock_client = MagicMock()
    mock_client.graph_query = AsyncMock(return_value={"rows": []})
    with patch.object(server, "_get_client", return_value=mock_client):
        await server.graph_query(cypher="MATCH (n) RETURN n")
    mock_client.graph_query.assert_called_once_with(cypher="MATCH (n) RETURN n", params=None)
