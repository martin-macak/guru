import asyncio

from guru_mcp.server import mcp


def test_mcp_server_has_tools():
    """Verify all expected tools are registered."""
    tools = asyncio.run(mcp.list_tools())
    tool_names = [tool.name for tool in tools]
    assert "search" in tool_names
    assert "get_document" in tool_names
    assert "list_documents" in tool_names
    assert "get_section" in tool_names
    assert "index_status" in tool_names


def test_mcp_server_name():
    assert mcp.name == "guru"
