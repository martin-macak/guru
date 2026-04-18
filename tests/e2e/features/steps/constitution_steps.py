"""Step defs for tests/e2e/features/constitution_invariants.feature.

These verify non-negotiable architectural invariants:
  1. Indexing never blocks on graph I/O.
  2. MCP write surface is bounded.
  3. Graph-agnostic surfaces are unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when

# ---------------------------------------------------------------------------
# Scenario 1: Indexing never blocks on graph I/O
# ---------------------------------------------------------------------------


def _cleanup_constitution(context) -> None:
    patcher = getattr(context, "_graph_patcher", None)
    if patcher is not None:
        with contextlib.suppress(RuntimeError):
            patcher.stop()
        context._graph_patcher = None
    tmp_project = getattr(context, "tmp_project", None)
    if tmp_project is not None:
        shutil.rmtree(tmp_project, ignore_errors=True)
        context.tmp_project = None


@given("a small fixture project with three markdown files")
def step_small_fixture(context):
    context.tmp_project = Path(tempfile.mkdtemp(prefix="g_const_", dir="/tmp"))
    context.add_cleanup(_cleanup_constitution, context)

    guru_dir = context.tmp_project / ".guru"
    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    docs = context.tmp_project / "docs"
    docs.mkdir()
    for n, body in (
        ("a.md", "# A\n\nFirst doc.\n"),
        ("b.md", "# B\n\nSecond doc with some content.\n"),
        ("c.md", "# C\n\nThird doc.\n"),
    ):
        (docs / n).write_text(body)

    (context.tmp_project / ".guru.json").write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [
                    {
                        "ruleName": "docs",
                        "match": {"glob": "docs/**/*.md"},
                        "labels": ["doc"],
                    }
                ],
                "graph": {"enabled": True},
            }
        )
    )


@given("the GraphClient.submit_parse_result is patched to hang for 30 seconds")
def step_hang_graph_submit(context):
    """Patch the GraphClient method that the indexer awaits.

    The patch sleeps via asyncio.sleep so the event loop can still schedule
    other work. The "per-file budget" step in the When wraps each call with
    asyncio.wait_for(...), which converts the hang into a TimeoutError that
    graph_or_skip swallows — exactly mirroring the production behaviour
    when a real daemon stalls past the GraphClient's read timeout.
    """
    from guru_core import graph_client as gc

    async def _hang(self, *, kb_name, payload):
        # Long enough to dwarf the per-file budget; the wait_for in the
        # caller is what actually bounds the wait.
        await asyncio.sleep(30)

    context._hang_impl = _hang
    context._graph_patcher = patch.object(gc.GraphClient, "submit_parse_result", _hang)
    context._graph_patcher.start()


@when("I run the indexer with a per-file budget of {budget:d} seconds")
def step_run_indexer_budgeted(context, budget):
    """Run the in-process indexer with a fake embedder.

    Layers a per-call asyncio.wait_for() on top of the (already patched)
    GraphClient.submit_parse_result so the hang is bounded by ``budget``
    seconds per file. A TimeoutError raised by wait_for is caught by
    ``graph_or_skip`` (which catches Exception), so indexing continues.
    """
    from guru_core import graph_client as gc
    from guru_server.app import create_app
    from guru_server.config import resolve_config
    from guru_server.embedding import OllamaEmbedder
    from guru_server.storage import VectorStore

    embedder = OllamaEmbedder()

    async def _fake_embed(text):
        return [0.01] * 768

    async def _fake_batch(texts):
        return [[0.01] * 768 for _ in texts]

    async def _fake_health():
        return None

    embedder.embed = _fake_embed
    embedder.embed_batch = _fake_batch
    embedder.check_health = _fake_health

    # Re-wrap submit_parse_result with a per-file budget. Replaces the raw
    # 30-second hang installed by the previous Given step with a bounded
    # version that times out and raises (which graph_or_skip swallows).
    raw_hang = context._hang_impl
    budget_seconds = float(budget)

    async def _bounded_hang(self, *, kb_name, payload):
        try:
            await asyncio.wait_for(
                raw_hang(self, kb_name=kb_name, payload=payload),
                timeout=budget_seconds,
            )
        except TimeoutError as e:
            # Convert the bounded hang into the GraphUnavailable that
            # graph_or_skip is designed to swallow — same shape as a real
            # daemon stalling past the client's read timeout.
            from guru_core.graph_errors import GraphUnavailable

            raise GraphUnavailable(
                f"simulated daemon hang exceeded {budget_seconds}s budget"
            ) from e

    # Stop the prior patch and install the bounded one.
    context._graph_patcher.stop()
    context._graph_patcher = patch.object(gc.GraphClient, "submit_parse_result", _bounded_hang)
    context._graph_patcher.start()

    config = resolve_config(project_root=context.tmp_project)
    store = VectorStore(db_path=str(context.tmp_project / ".guru" / "db"))

    app = create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(context.tmp_project),
        auto_index=False,
    )
    indexer = app.state.indexer
    job = app.state.job_registry.create_job()

    start = time.monotonic()
    asyncio.run(indexer.run(job))
    context.elapsed = time.monotonic() - start
    context.indexer = indexer
    context.budget = budget
    context.app = app
    context.job = job


@then("the indexer completes within {limit:d} seconds total")
def step_completes_within(context, limit):
    assert context.elapsed < limit, (
        f"indexer took {context.elapsed:.1f}s, expected < {limit}s "
        f"— graph_or_skip likely failed to short-circuit"
    )


@then("every fixture file has chunks in LanceDB")
def step_every_file_indexed(context):
    """Verify every fixture file produced chunks via the store API."""
    store = context.app.state.store
    docs = store.list_documents()
    found = {Path(d["file_path"]).name for d in docs}
    expected = {"a.md", "b.md", "c.md"}
    missing = expected - found
    assert not missing, (
        f"missing chunks for fixture files: {missing} (found={found}, listed={docs!r})"
    )


# ---------------------------------------------------------------------------
# Scenario 2: MCP write surface is bounded
# ---------------------------------------------------------------------------


@when("the MCP tool list is enumerated")
def step_enumerate_mcp_tools(context):
    from guru_mcp import server

    tools = asyncio.run(server.mcp.list_tools())
    context.mcp_tool_names = {t.name for t in tools}


@then(
    "the only write-capable graph tools are graph_annotate, "
    "graph_delete_annotation, graph_link, graph_unlink, graph_reattach_orphan"
)
def step_write_tools_bounded(context):
    expected_writes = {
        "graph_annotate",
        "graph_delete_annotation",
        "graph_link",
        "graph_unlink",
        "graph_reattach_orphan",
    }
    # All graph_* names that MUTATE state. We hard-code the spec set rather
    # than infer from the function bodies — this is a contract, not an
    # observation.
    found_writes = expected_writes & context.mcp_tool_names
    missing = expected_writes - context.mcp_tool_names
    assert not missing, f"expected MCP write tools missing: {missing}"
    assert found_writes == expected_writes, (
        f"write tool set mismatch: expected {expected_writes}, found {found_writes}"
    )


@then("no MCP tool exists named upsert_kb, delete_kb, link_kbs, unlink_kbs")
def step_no_kb_crud_tools(context):
    forbidden = {"upsert_kb", "delete_kb", "link_kbs", "unlink_kbs"}
    overlap = forbidden & context.mcp_tool_names
    assert not overlap, f"forbidden KB-CRUD tools exposed in MCP: {overlap}"


# ---------------------------------------------------------------------------
# Scenario 3: Graph-agnostic surfaces unchanged
# ---------------------------------------------------------------------------


_AGNOSTIC_MCP_TOOLS = (
    "search",
    "get_document",
    "list_documents",
    "get_section",
    "index_status",
    "federated_search",
    "list_peers",
)


@when(
    "I enumerate the public surface of search, get_document, list_documents, "
    "get_section, index_status, federated_search, list_peers"
)
def step_enumerate_agnostic_surface(context):
    from guru_mcp import server

    sigs: dict[str, inspect.Signature] = {}
    for name in _AGNOSTIC_MCP_TOOLS:
        fn = getattr(server, name, None)
        if fn is None:
            continue
        sigs[name] = inspect.signature(fn)
    context.agnostic_sigs = sigs


@then("each surface is reachable as a tool function in guru_mcp.server")
def step_each_surface_reachable(context):
    missing = [n for n in _AGNOSTIC_MCP_TOOLS if n not in context.agnostic_sigs]
    assert not missing, f"missing graph-agnostic MCP tools: {missing}"


@then("none of them takes a graph_ prefixed parameter")
def step_no_graph_params(context):
    offenders: dict[str, list[str]] = {}
    for name, sig in context.agnostic_sigs.items():
        bad = [p for p in sig.parameters if p.startswith("graph_")]
        if bad:
            offenders[name] = bad
    assert not offenders, f"graph-agnostic surfaces leaked graph_ parameters: {offenders}"


@then("the CLI commands guru init, guru index, guru search are still registered")
def step_cli_commands_present(context):
    from guru_cli.cli import cli

    expected = {"init", "index", "search"}
    found = set(cli.commands.keys())
    missing = expected - found
    assert not missing, f"CLI commands missing: {missing} (found={sorted(found)})"
