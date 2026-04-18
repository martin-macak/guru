"""Step definitions for MCP tool scenarios.

Uses FastMCP's in-memory Client to call MCP tools directly.
The MCP tools connect to the real guru-server over UDS.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from behave import given, then, when
from fastmcp import Client

from guru_core.client import GuruClient
from guru_mcp.server import mcp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _get_mcp_client(context):
    """Return a patched MCP Client that routes to the test server."""
    project_dir = context.project_dir

    def _patched_get_client():
        if hasattr(context, "guru_client"):
            return context.guru_client
        return GuruClient(guru_root=project_dir)

    context._mcp_patcher = patch("guru_mcp.server._get_client", _patched_get_client)
    context._mcp_patcher.start()
    return Client(mcp)


async def _call_tool(client, tool_name: str, arguments: dict | None = None):
    """Call an MCP tool and return the parsed result.

    FastMCP Client.call_tool returns a CallToolResult with a .data attribute
    when wrap_result is True (the default). Fall back to parsing .content
    text blocks if .data is not available.
    """
    async with client:
        result = await client.call_tool(tool_name, arguments or {})

    # Prefer .data (FastMCP's auto-parsed result)
    if hasattr(result, "data") and result.data is not None:
        return result.data

    # Fall back to parsing text content blocks
    if hasattr(result, "content"):
        for block in result.content:
            if hasattr(block, "text"):
                return json.loads(block.text)

    return result


# ---------------------------------------------------------------------------
# GIVEN steps
# ---------------------------------------------------------------------------


@given("the MCP server is connected")
def step_mcp_connected(context):
    """Create an MCP client connected to the guru MCP server."""
    context.mcp_client = _get_mcp_client(context)


@given("the knowledge base has been indexed via MCP")
def step_index_via_rest(context):
    """Index the knowledge base by calling the server REST API directly."""
    import time

    client = (
        context.guru_client
        if hasattr(context, "guru_client")
        else GuruClient(guru_root=context.project_dir)
    )
    asyncio.run(client.trigger_index())

    # Wait for background indexing to complete
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        status = asyncio.run(client.status())
        if status.get("current_job") is None and status.get("chunk_count", 0) > 0:
            break
        time.sleep(0.3)
    else:
        raise RuntimeError("Indexing did not complete within timeout")


@given('I know the file path of a document matching "{fragment}"')
def step_find_doc_path(context, fragment):
    """List documents via REST and find one matching the fragment."""
    client = (
        context.guru_client
        if hasattr(context, "guru_client")
        else GuruClient(guru_root=context.project_dir)
    )
    docs = _run(client.list_documents())
    for doc in docs:
        if fragment in doc["file_path"]:
            context.known_file_path = doc["file_path"]
            return
    raise AssertionError(f"No document matching '{fragment}' found in: {docs}")


@given('I know a section header containing "{fragment}"')
def step_find_section_header(context, fragment):
    """Find a section header by searching all indexed chunks.

    Uses a broad search to scan all chunks, looking for the fragment
    in the header_breadcrumb. Works with fake embeddings since we
    search with high n_results to get all chunks.
    """
    client = (
        context.guru_client
        if hasattr(context, "guru_client")
        else GuruClient(guru_root=context.project_dir)
    )
    # Get all chunks — with fake embeddings this returns everything
    results = _run(client.search("a", n_results=100))
    for r in results:
        if fragment.lower() in r.get("header_breadcrumb", "").lower():
            context.known_header = r["header_breadcrumb"]
            return
    breadcrumbs = [r.get("header_breadcrumb", "") for r in results]
    raise AssertionError(f"No header containing '{fragment}'. Available: {breadcrumbs}")


# ---------------------------------------------------------------------------
# WHEN steps
# ---------------------------------------------------------------------------


@when('I call MCP tool "{tool_name}" with no arguments')
def step_call_mcp_no_args(context, tool_name):
    """Call an MCP tool with no arguments."""
    try:
        context.mcp_result = _run(_call_tool(context.mcp_client, tool_name))
        context.mcp_error = None
    except Exception as e:
        context.mcp_result = None
        context.mcp_error = e


@when('I call MCP tool "{tool_name}" with query "{query}"')
def step_call_mcp_search(context, tool_name, query):
    """Call an MCP search tool with a query."""
    try:
        context.mcp_result = _run(_call_tool(context.mcp_client, tool_name, {"query": query}))
        context.mcp_error = None
    except Exception as e:
        context.mcp_result = None
        context.mcp_error = e


@when('I call MCP tool "{tool_name}" with query "{query}" and n_results {n:d}')
def step_call_mcp_search_limited(context, tool_name, query, n):
    """Call an MCP search tool with a query and result limit."""
    try:
        context.mcp_result = _run(
            _call_tool(context.mcp_client, tool_name, {"query": query, "n_results": n})
        )
        context.mcp_error = None
    except Exception as e:
        context.mcp_result = None
        context.mcp_error = e


@when('I call MCP tool "get_document" with the known file path')
def step_call_mcp_get_document(context):
    """Call get_document with the file path found in a previous step."""
    try:
        context.mcp_result = _run(
            _call_tool(context.mcp_client, "get_document", {"file_path": context.known_file_path})
        )
        context.mcp_error = None
    except Exception as e:
        context.mcp_result = None
        context.mcp_error = e


@when('I call MCP tool "get_section" with the known file path and header')
def step_call_mcp_get_section(context):
    """Call get_section with file path and header from previous steps."""
    try:
        context.mcp_result = _run(
            _call_tool(
                context.mcp_client,
                "get_section",
                {"file_path": context.known_file_path, "header_path": context.known_header},
            )
        )
        context.mcp_error = None
    except Exception as e:
        context.mcp_result = None
        context.mcp_error = e


@when("I retrieve the document from the first search result via MCP")
def step_retrieve_first_result(context):
    """Take the file_path from the first search result and call get_document."""
    assert isinstance(context.mcp_result, list), "Previous result was not a list"
    assert len(context.mcp_result) > 0, "Previous search returned no results"
    file_path = context.mcp_result[0]["file_path"]
    try:
        context.mcp_result = _run(
            _call_tool(context.mcp_client, "get_document", {"file_path": file_path})
        )
        context.mcp_error = None
    except Exception as e:
        context.mcp_result = None
        context.mcp_error = e


# ---------------------------------------------------------------------------
# THEN steps
# ---------------------------------------------------------------------------


@then("the MCP call succeeds")
def step_mcp_succeeds(context):
    assert context.mcp_error is None, f"MCP call failed: {context.mcp_error}"
    assert context.mcp_result is not None, "MCP call returned None"


@then("the MCP result is a non-empty list")
def step_mcp_result_nonempty_list(context):
    assert isinstance(context.mcp_result, list), (
        f"Expected list, got {type(context.mcp_result)}: {context.mcp_result}"
    )
    assert len(context.mcp_result) > 0, "MCP result list is empty"


@then("the MCP result is a list with {n:d} items")
def step_mcp_result_list_count(context, n):
    assert isinstance(context.mcp_result, list), f"Expected list, got {type(context.mcp_result)}"
    assert len(context.mcp_result) == n, f"Expected {n} items, got {len(context.mcp_result)}"


@then("the MCP result has at most {n:d} items")
def step_mcp_result_at_most(context, n):
    assert isinstance(context.mcp_result, list), f"Expected list, got {type(context.mcp_result)}"
    assert len(context.mcp_result) <= n, (
        f"Expected at most {n} items, got {len(context.mcp_result)}"
    )


@then('the MCP result has field "{field}"')
def step_mcp_result_has_field(context, field):
    assert isinstance(context.mcp_result, dict), (
        f"Expected dict, got {type(context.mcp_result)}: {context.mcp_result}"
    )
    assert field in context.mcp_result, (
        f"Field '{field}' not in result. Keys: {list(context.mcp_result.keys())}"
    )


@then('the MCP result field "{field}" is "{value}"')
def step_mcp_result_field_equals_str(context, field, value):
    actual = str(context.mcp_result.get(field))
    assert actual == value, f"Expected {field}='{value}', got '{actual}'"


@then('the MCP result field "{field}" is greater than {n:d}')
def step_mcp_result_field_gt(context, field, n):
    actual = context.mcp_result.get(field)
    assert actual is not None, f"Field '{field}' is None"
    assert int(actual) > n, f"Expected {field} > {n}, got {actual}"


@then('the MCP result field "{field}" equals {n:d}')
def step_mcp_result_field_eq_int(context, field, n):
    actual = context.mcp_result.get(field)
    assert actual is not None, f"Field '{field}' is None"
    assert int(actual) == n, f"Expected {field} == {n}, got {actual}"


@then('the MCP result field "{field}" contains "{text}"')
def step_mcp_result_field_contains(context, field, text):
    actual = context.mcp_result.get(field)
    assert actual is not None, f"Field '{field}' is None"
    actual_str = str(actual)
    assert text in actual_str, f"Expected '{text}' in {field}, got: {actual_str[:200]}"


@then('the first MCP result has field "{field}"')
def step_first_mcp_result_has_field(context, field):
    assert isinstance(context.mcp_result, list) and len(context.mcp_result) > 0
    first = context.mcp_result[0]
    assert field in first, f"Field '{field}' not in first result. Keys: {list(first.keys())}"


@then('the first MCP result field "{field}" contains "{text}"')
def step_first_mcp_result_field_contains(context, field, text):
    assert isinstance(context.mcp_result, list) and len(context.mcp_result) > 0
    first = context.mcp_result[0]
    actual = str(first.get(field, ""))
    assert text in actual, f"Expected '{text}' in first result's {field}, got: {actual[:200]}"


@then('some MCP result has label "{label}"')
def step_some_result_has_label(context, label):
    """Check that at least one result in the list has the given label."""
    assert isinstance(context.mcp_result, list), "Result is not a list"
    for item in context.mcp_result:
        labels = item.get("labels", [])
        if isinstance(labels, str | list) and label in labels:
            return
    all_labels = [item.get("labels") for item in context.mcp_result]
    raise AssertionError(f"No result has label '{label}'. Labels found: {all_labels}")


@then('the MCP result contains an item with file_path matching "{fragment}"')
def step_mcp_result_contains_path(context, fragment):
    assert isinstance(context.mcp_result, list)
    paths = [item.get("file_path", "") for item in context.mcp_result]
    assert any(fragment in p for p in paths), (
        f"No item with file_path matching '{fragment}'. Paths: {paths}"
    )
