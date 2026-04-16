import asyncio

from guru_mcp.server import mcp

EXPECTED_TOOLS = [
    "search",
    "get_document",
    "list_documents",
    "get_section",
    "index_status",
    "federated_search",
    "clone_codebase",
    "unmount_codebase",
    "list_peers",
]


def test_mcp_server_has_all_tools():
    tools = asyncio.run(mcp.list_tools())
    tool_names = [tool.name for tool in tools]
    for expected in EXPECTED_TOOLS:
        assert expected in tool_names, f"Missing MCP tool: {expected}"


def test_mcp_server_name():
    assert mcp.name == "guru"


def test_get_document_has_server_name_param():
    tools = asyncio.run(mcp.list_tools())
    get_doc = next(t for t in tools if t.name == "get_document")
    schema = get_doc.parameters
    assert "server_name" in schema.get("properties", {})


def test_get_section_has_server_name_param():
    tools = asyncio.run(mcp.list_tools())
    get_sec = next(t for t in tools if t.name == "get_section")
    schema = get_sec.parameters
    assert "server_name" in schema.get("properties", {})
