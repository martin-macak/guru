"""Step definitions for the PR-5 scenarios in graph_optional.feature.

Two scenarios:
  - "Graph MCP tools return status, not error, when disabled" — call the
    four MCP tools (graph_describe / graph_find / graph_orphans /
    graph_annotate) against a running guru-server with graph disabled.
    The proxy short-circuits to ``{"status":"graph_disabled"}``.
  - "CLI graph commands exit 0 when graph disabled" — invoke
    ``guru graph orphans`` as a subprocess (cwd = the project tmpdir whose
    ``.guru.json`` has ``graph.enabled=false``) and assert exit 0 with the
    documented message on stdout.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from unittest.mock import patch

from behave import then, when

from guru_core.client import GuruClient

# ---------------------------------------------------------------------------
# WHEN — MCP tools against graph-disabled server
# ---------------------------------------------------------------------------


@when("MCP calls graph_describe, graph_find, graph_orphans, graph_annotate")
def step_call_four_mcp_tools_disabled(context):
    """Invoke each of the four read/write graph MCP tools.

    The tools return whatever ``GuruClient.graph_*`` returns. With graph
    disabled, the server's ``/graph/*`` proxy short-circuits to
    ``{"status": "graph_disabled"}`` (see ``guru_server.api.graph``).

    We patch ``_get_client`` to point the MCP server at the running test
    server (project_dir's UDS socket) — same trick used by mcp_steps.py.
    """
    from guru_mcp import server as mcp_server

    project_dir = context.project_dir

    def _patched_get_client() -> GuruClient:
        return GuruClient(guru_root=project_dir)

    context._mcp_patcher = patch.object(mcp_server, "_get_client", _patched_get_client)
    context._mcp_patcher.start()

    async def _call_all() -> dict:
        return {
            "describe": await mcp_server.graph_describe(node_id="anything::x"),
            "find": await mcp_server.graph_find(name="x"),
            "orphans": await mcp_server.graph_orphans(),
            "annotate": await mcp_server.graph_annotate(
                node_id="anything::x", kind="note", body="x"
            ),
        }

    context.mcp_results = asyncio.run(_call_all())
    context.mcp_error = None


@when("I run 'guru graph orphans'")
def step_run_guru_graph_orphans(context):
    """Run the CLI subcommand against the project tmpdir (graph.enabled=false).

    Inherits the behave env so XDG dirs etc. point at the isolated test
    home (set by ``before_feature`` for the polyglot-fixture features).
    """
    result = subprocess.run(
        ["uv", "run", "guru", "graph", "orphans"],
        capture_output=True,
        text=True,
        cwd=str(context.project_dir),
        env=os.environ.copy(),
        timeout=60,
    )
    context.cli_exit = result.returncode
    context.cli_out = result.stdout + result.stderr


# ---------------------------------------------------------------------------
# THEN — assertions
# ---------------------------------------------------------------------------


@then('each returns {"status":"graph_disabled", ...}')
def step_each_returns_graph_disabled(context):
    """Every MCP tool call returned a dict containing ``status:graph_disabled``."""
    results = context.mcp_results
    for tool_name, body in results.items():
        assert isinstance(body, dict), (
            f"{tool_name} returned non-dict {type(body).__name__}: {body!r}"
        )
        assert body.get("status") == "graph_disabled", (
            f"{tool_name} did not return graph_disabled status. Got: {body!r}"
        )


@then("none raise exceptions")
def step_none_raise(context):
    """All tool invocations completed without raising."""
    assert context.mcp_error is None, f"MCP call raised: {context.mcp_error!r}"


@then("exit code is 0")
def step_cli_exit_zero(context):
    assert context.cli_exit == 0, (
        f"expected exit code 0, got {context.cli_exit}\nOutput:\n{context.cli_out}"
    )


@then('stdout contains "{text}"')
def step_stdout_contains(context, text):
    assert text in context.cli_out, f"expected {text!r} in CLI output, got:\n{context.cli_out}"
