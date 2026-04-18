"""Step definitions for graph_cli_reads.feature.

These steps invoke `uv run guru graph ...` as a real subprocess — exercising
the installed console-script entrypoint rather than mocking the click
callback — because BDD acceptance tests need to verify the end-to-end
user-visible behavior, not just the call graph.

Scenarios tagged @real_neo4j require a running Neo4j (for example via
scripts/start-test-neo4j.sh) plus GURU_REAL_NEO4J=1 and
GURU_NEO4J_BOLT_URI pointed at that Neo4j. They're auto-skipped by the
before_feature hook in environment.py when that env isn't set.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess

from behave import given, then, when


def _run_guru_graph(args: list[str]) -> tuple[int, str]:
    """Invoke `uv run guru graph <args>` and return (exit_code, stdout+stderr).

    Inherits the behave env (GURU_GRAPH_HOME, GURU_NEO4J_BOLT_URI etc.).
    """
    result = subprocess.run(
        ["uv", "run", "guru", "graph", *args],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given("no graph daemon is running and no sockets exist")
def step_no_daemon(context):
    """Remove any stale socket / pid files so the CLI can't accidentally
    find a previous run's state.
    """
    from guru_graph.config import GraphPaths
    from guru_graph.lifecycle import read_pid_file

    paths = GraphPaths.default()
    pid = read_pid_file(paths.pid_file)
    if pid is not None:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, 15)
    for p in (paths.socket, paths.pid_file):
        with contextlib.suppress(FileNotFoundError):
            p.unlink()


@given('a running guru-graph daemon with a KB "{name}" upserted')
def step_daemon_with_kb(context, name):
    """Spawn the daemon (lazy-start via connect_or_spawn) and upsert a KB."""
    from guru_core.graph_client import GraphClient
    from guru_core.graph_types import KbUpsert
    from guru_graph.config import GraphPaths
    from guru_graph.lifecycle import connect_or_spawn

    paths = GraphPaths.default()
    connect_or_spawn(paths=paths, ready_timeout_seconds=60.0)
    client = GraphClient(socket_path=str(paths.socket), auto_start=False)
    asyncio.run(
        client.upsert_kb(KbUpsert(name=name, project_root=f"/tmp/{name}")),
    )
    context.graph_kb_name = name


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when("I run the graph help command")
def step_run_graph_help(context):
    code, out = _run_guru_graph(["--help"])
    context.graph_exit = code
    context.graph_out = out


@when("I run the graph query help command")
def step_run_graph_query_help(context):
    code, out = _run_guru_graph(["query", "--help"])
    context.graph_exit = code
    context.graph_out = out


@when('I run the graph command "{cmdline}"')
def step_run_graph_cmd(context, cmdline):
    """Split on shell-style whitespace, respecting single-quoted segments.

    Intentionally simple — scenarios only use ASCII + single-quote-wrapped
    args like 'MATCH (n) RETURN n'. Full shell parsing is overkill.
    """
    import shlex

    args = shlex.split(cmdline)
    code, out = _run_guru_graph(args)
    context.graph_exit = code
    context.graph_out = out


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


@then('the graph help output lists "{name}"')
def step_help_lists(context, name):
    assert name in context.graph_out, (
        f"Expected subcommand '{name}' in help output:\n{context.graph_out}"
    )


@then('the graph help output contains "{text}"')
def step_help_contains(context, text):
    assert text in context.graph_out, f"Expected '{text}' in help output:\n{context.graph_out}"


@then('the graph help output does not contain "{text}"')
def step_help_not_contains(context, text):
    assert text not in context.graph_out, (
        f"Unexpected '{text}' in help output:\n{context.graph_out}"
    )


@then("the graph command exits with code {code:d}")
def step_graph_exit_code(context, code):
    assert context.graph_exit == code, (
        f"Expected exit {code}, got {context.graph_exit}:\n{context.graph_out}"
    )


@then('the graph command output contains "{text}"')
def step_graph_out_contains(context, text):
    assert text in context.graph_out, f"Expected '{text}' in output:\n{context.graph_out}"


@then("the graph command output is a JSON array of length {n:d}")
def step_graph_out_json_array(context, n):
    # The CLI prints JSON on stdout and may log to stderr; find the array
    # block by trimming until we find a '[' and parsing from there.
    text = context.graph_out
    start = text.find("[")
    assert start != -1, f"No JSON array found in output:\n{text}"
    data = json.loads(text[start:].split("\n(no")[0])  # guard against trailer
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    assert len(data) == n, f"Expected length {n}, got {len(data)}:\n{data}"
    context.graph_parsed_json = data


@then('the first graph JSON item has name "{name}"')
def step_first_json_item_name(context, name):
    first = context.graph_parsed_json[0]
    assert first.get("name") == name, f"Expected name={name!r}, got {first.get('name')!r}"
