"""Step definitions for artifact_indexing.feature and graph_optional.feature.

The Markdown-only subset + graph_optional scenarios are fully implemented here.
Python- and OpenAPI-dependent scenarios (tagged @skip_until_pr7 / @skip_until_pr8)
are specified in the feature files but their steps live in later-PR step files.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from behave import given, then, when

_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_path(project_dir: Path) -> Path:
    """Return the preferred local config path for a fixture project."""
    for name in (".guru.json", "guru.json"):
        path = project_dir / name
        if path.exists():
            return path
    # Fall back to .guru.json (preferred dotfile) if none exist yet.
    return project_dir / ".guru.json"


def _load_config(project_dir: Path) -> dict:
    path = _config_path(project_dir)
    if path.exists():
        return json.loads(path.read_text())
    return {"version": 1}


def _save_config(project_dir: Path, config: dict) -> None:
    path = _config_path(project_dir)
    path.write_text(json.dumps(config, indent=2) + "\n")


def _set_graph_enabled(project_dir: Path, enabled: bool) -> None:
    config = _load_config(project_dir)
    config.setdefault("version", 1)
    config["graph"] = {"enabled": enabled}
    _save_config(project_dir, config)


def _start_server_for_context(context) -> None:
    """Start a guru-server for context.project_dir, shutting down any prior one."""
    from environment import _make_fake_embedder, _start_server

    # Ensure .guru/ and .guru/db exist (fixture comes without them).
    guru_dir = context.project_dir / ".guru"
    guru_dir.mkdir(exist_ok=True)
    (guru_dir / "db").mkdir(exist_ok=True)

    # Tear down any existing server bound to this project dir.
    _stop_server_for_context(context)

    if not getattr(context, "embedder", None):
        context.embedder = _make_fake_embedder()
    context.server, context.server_thread = _start_server(context.project_dir, context.embedder)


def _stop_server_for_context(context) -> None:
    server = getattr(context, "server", None)
    thread = getattr(context, "server_thread", None)
    if server is not None:
        server.should_exit = True
    if thread is not None:
        thread.join(timeout=5)
    context.server = None
    context.server_thread = None

    if getattr(context, "project_dir", None) is not None:
        sock = context.project_dir / ".guru" / "guru.sock"
        pid = context.project_dir / ".guru" / "guru.pid"
        with contextlib.suppress(FileNotFoundError):
            sock.unlink()
        with contextlib.suppress(FileNotFoundError):
            pid.unlink()


def _trigger_index_and_wait(context, timeout: float = 60.0) -> dict:
    from environment import _trigger_and_wait_index

    job = _trigger_and_wait_index(context.project_dir, timeout=timeout)
    context.last_index_job = job
    return job


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given('the "{name}" fixture project is copied to a tmpdir')
def step_copy_fixture(context, name):
    src = _FIXTURES_DIR / name
    assert src.is_dir(), f"Fixture {name!r} not found at {src}"

    tmp_root = Path(tempfile.mkdtemp(prefix=f"g_{name}_", dir="/tmp"))
    dst = tmp_root / name
    shutil.copytree(src, dst)
    context.project_dir = dst
    context._polyglot_tmp_root = tmp_root


@given("graph is enabled")
def step_graph_enabled(context):
    _set_graph_enabled(context.project_dir, True)
    _start_server_for_context(context)


@given("graph is disabled")
def step_graph_disabled(context):
    _set_graph_enabled(context.project_dir, False)
    _start_server_for_context(context)


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when("I run 'guru index'")
def step_run_index(context):
    context.last_index_job = _trigger_index_and_wait(context)


# ---------------------------------------------------------------------------
# THEN — graph_optional subset (no Neo4j required)
# ---------------------------------------------------------------------------


@then("the index command succeeds")
def step_index_ok(context):
    job = getattr(context, "last_index_job", None)
    assert job is not None, "no index job recorded"
    assert job.get("status") == "completed", (
        f"expected status=completed, got {job.get('status')}: {job}"
    )


@then("the server status reports graph_reachable = {val}")
def step_server_status_graph_reachable(context, val):
    import httpx

    socket_path = str(context.project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        data = client.get("http://localhost/status").json()
    expected = val.lower() in ("true", "yes", "1")
    assert bool(data.get("graph_reachable")) is expected, (
        f"graph_reachable={data.get('graph_reachable')}, expected {expected}: {data}"
    )


@then("the server status reports graph_enabled = {val}")
def step_server_status_graph_enabled(context, val):
    import httpx

    socket_path = str(context.project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        data = client.get("http://localhost/status").json()
    expected = val.lower() in ("true", "yes", "1")
    assert bool(data.get("graph_enabled")) is expected, (
        f"graph_enabled={data.get('graph_enabled')}, expected {expected}: {data}"
    )


@then("no guru-graph daemon was spawned")
def step_no_daemon_spawned(context):
    """With graph disabled, the server should not spawn the graph daemon.

    We verify indirectly: the server's graph_client is None (see next step)
    AND no daemon socket/pid was created under the isolated GURU_GRAPH_HOME
    (if the surrounding test harness set one). This scenario only runs under
    the default configuration so we assert the app-level invariant.
    """
    import httpx

    socket_path = str(context.project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        data = client.get("http://localhost/status").json()
    # If the daemon had been spawned, graph_reachable would be true.
    assert data.get("graph_reachable") is False, f"graph unexpectedly reachable: {data}"


@then("the server's graph client is None")
def step_graph_client_is_none(context):
    """When config disables the graph, the app builds no GraphClient."""
    import httpx

    socket_path = str(context.project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        data = client.get("http://localhost/status").json()
    assert data.get("graph_enabled") is False, f"expected graph_enabled=False, got {data}"
    assert data.get("graph_reachable") is False, f"expected graph_reachable=False, got {data}"


# ---------------------------------------------------------------------------
# THEN — artifact_indexing (Markdown-only subset, @real_neo4j)
# ---------------------------------------------------------------------------


def _neo4j_driver():
    """Return a Neo4j driver pointed at GURU_NEO4J_BOLT_URI or default localhost."""
    from neo4j import GraphDatabase

    uri = os.environ.get("GURU_NEO4J_BOLT_URI", "bolt://127.0.0.1:7687")
    return GraphDatabase.driver(uri, auth=None)


@then('(:Document {{id: "{doc_id}"}}) exists in the graph')
def step_document_exists(context, doc_id):
    driver = _neo4j_driver()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (d:Document {id: $id}) RETURN d.id AS id",
                id=doc_id,
            )
            records = list(result)
            assert records, f"no Document with id={doc_id!r} found in the graph"
    finally:
        driver.close()


@then("at least one (:MarkdownSection) node under {rel_path} exists")
def step_markdown_sections_exist(context, rel_path):
    driver = _neo4j_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)-[:CONTAINS*1..]->(s:MarkdownSection)
                WHERE d.relative_path = $rel_path
                RETURN count(s) AS n
                """,
                rel_path=rel_path,
            )
            record = result.single()
            n = record["n"] if record else 0
            assert n > 0, f"no MarkdownSection nodes under {rel_path!r} (count={n})"
    finally:
        driver.close()


@then('LanceDB contains chunks for {rel_path} with kind="{kind}"')
def step_lancedb_has_chunks(context, rel_path, kind):
    import lancedb

    db_path = context.project_dir / ".guru" / "db"
    db = lancedb.connect(str(db_path))
    try:
        tables = db.table_names()
    except Exception:
        tables = []
    assert tables, f"no LanceDB tables found under {db_path}"
    # The chunks table is typically named "chunks" in guru-server. Fall back
    # to the first table if naming differs — scenario-level assertions only
    # care about chunk content, not the table name.
    table_name = "chunks" if "chunks" in tables else tables[0]
    table = db.open_table(table_name)
    df = table.to_pandas()
    # file_path is stored as the absolute on-disk path — use suffix match.
    mask_path = df["file_path"].astype(str).str.endswith(rel_path)
    mask_kind = df["kind"].astype(str) == kind
    matching = df[mask_path & mask_kind]
    assert len(matching) > 0, (
        f"no LanceDB rows match file_path~={rel_path!r} kind={kind!r}; "
        f"columns present: {list(df.columns)}; "
        f"unique kinds: {sorted(df['kind'].astype(str).unique().tolist())}"
    )


# ---------------------------------------------------------------------------
# Fallback "I run 'guru X'" via CLI subprocess (not used by the PR-2 subset
# but handy for future scenarios).
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["uv", "run", "guru", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=os.environ.copy(),
        timeout=60,
    )
    return result.returncode, result.stdout + result.stderr
