"""Steps for parser_extensibility.feature.

Two scenarios:

* @real_neo4j: register a test ProtobufParser into the parser registry of a
  freshly-built guru-server, run the indexer once on a fixture project that
  contains a single .proto file, and assert that the parser was dispatched
  and that LanceDB stored a chunk with language=protobuf.

* default: smoke test that ProtobufParser.supports() correctly accepts .proto
  and rejects .py — the cheapest way to confirm the fixture parser is
  importable and the DocumentParser protocol contract still holds.

The fixture parser lives under ``tests/e2e/fixtures/protobuf_parser`` and is
imported by adding ``tests/e2e/fixtures`` to ``sys.path``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from behave import given, then, when

# Add the fixtures dir to sys.path so the test ProtobufParser is importable.
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))

from protobuf_parser.parser import ProtobufParser  # noqa: E402

# ---------------------------------------------------------------------------
# Scenario 1 — registration via init hook + indexer dispatch
# ---------------------------------------------------------------------------


@given("the test registers ProtobufParser into the shared ParserRegistry via the init hook")
def step_register_protobuf_parser(context):
    """Patch guru_server.app.create_app so the freshly-built FastAPI app gets
    the test ProtobufParser appended to its parser registry.

    Restored in after-scenario cleanup so other features don't see it.
    """
    # Reset the call log so every scenario starts clean.
    ProtobufParser.parse_call_log.clear()

    from guru_server import app as server_app

    original = server_app.create_app

    def wrapped(*args, **kwargs):
        fastapi_app = original(*args, **kwargs)
        fastapi_app.state.parser_registry.register(ProtobufParser())
        # Re-point the indexer at the (mutated) registry so dispatch sees it.
        if fastapi_app.state.indexer is not None:
            fastapi_app.state.indexer._registry = fastapi_app.state.parser_registry
        return fastapi_app

    context._original_create_app = original
    server_app.create_app = wrapped


@given('a fixture project has a file "{rel}" with proto content')
def step_fixture_proto(context, rel):
    """Lay out a minimal guru project under /tmp containing a .proto file.

    The macOS AF_UNIX 104-byte limit forces us to use /tmp (not $TMPDIR).
    """
    context.tmp_project = Path(tempfile.mkdtemp(prefix="g_proto_", dir="/tmp"))

    # Copy the proto source from the fixture dir.
    src = _FIXTURES / "protobuf_parser" / "user.proto"
    dest = context.tmp_project / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text())

    # Bare .guru / .guru/db dirs and a config that matches the proto file.
    (context.tmp_project / ".guru").mkdir()
    (context.tmp_project / ".guru" / "db").mkdir()
    config = {
        "version": 1,
        "name": "proto-fixture",
        "rules": [
            {
                "ruleName": "proto",
                "match": {"glob": "**/*.proto"},
                "labels": ["proto"],
            }
        ],
        "graph": {"enabled": False},
    }
    (context.tmp_project / ".guru.json").write_text(json.dumps(config, indent=2))


@when("`guru index` runs against that fixture")
def step_index_runs(context):
    """Stand up a minimal guru-server on the tmp_project and run the indexer.

    We bypass the HTTP route and call indexer.run() directly since the only
    thing under test is parser dispatch + LanceDB persistence.
    """
    from environment import _make_fake_embedder

    from guru_server.app import create_app
    from guru_server.config import resolve_config
    from guru_server.storage import VectorStore

    embedder = _make_fake_embedder()

    socket_path = str(context.tmp_project / ".guru" / "guru.sock")
    config = resolve_config(project_root=context.tmp_project)
    store = VectorStore(db_path=str(context.tmp_project / ".guru" / "db"))

    app = create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(context.tmp_project),
        auto_index=False,
    )
    uvi_config = uvicorn.Config(app, uds=socket_path, log_level="warning")
    server = uvicorn.Server(uvi_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if Path(socket_path).exists():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("server didn't start in time")

    # Drive the indexer synchronously so the assertions below see the result.
    indexer = app.state.indexer
    job = app.state.job_registry.create_job()
    asyncio.run(indexer.run(job))

    context.server = server
    context.server_thread = thread
    context.indexer = indexer
    context.app = app
    context.last_job = job


@then('ProtobufParser.parse was called for "{rel}" exactly once')
def step_parse_called_once(context, rel):
    calls = [c for c in ProtobufParser.parse_call_log if c == rel or c.endswith(rel)]
    assert len(calls) == 1, (
        f"expected exactly 1 parse call for {rel!r}, got {ProtobufParser.parse_call_log!r}"
    )


@then('LanceDB contains a chunk for "{rel}" with parser_name "{name}"')
def step_lancedb_has_chunk(context, rel, name):
    """Query LanceDB directly for a chunk whose file_path ends with `rel`.

    `parser_name` lives on the Document graph node, not in the chunk row, so
    we assert language=<name> on the chunk side as the surrogate. Combined
    with the parse-call-log assertion above, this proves the parser ran end
    to end.
    """
    import lancedb

    db_path = context.tmp_project / ".guru" / "db"
    db = lancedb.connect(str(db_path))
    tables = db.table_names()
    assert "chunks" in tables, f"no chunks table — found {tables}"

    df = db.open_table("chunks").to_pandas()
    mask = df["file_path"].astype(str).str.endswith(rel)
    matching = df[mask]
    assert len(matching) > 0, (
        f"no LanceDB rows match file_path~={rel!r}; "
        f"file_paths in db: {df['file_path'].astype(str).tolist()}"
    )
    languages = set(matching["language"].astype(str).tolist())
    assert name in languages, (
        f"expected at least one chunk with language={name!r}, got {languages!r}"
    )

    # Cleanup — happens here because the second-scenario cleanup hook is in
    # the per-scenario after step below; the after_feature hook in
    # environment.py also wipes graph state.
    _cleanup_scenario(context)


# ---------------------------------------------------------------------------
# Scenario 2 — pure unit smoke check on supports()
# ---------------------------------------------------------------------------


@when("I instantiate ProtobufParser")
def step_instantiate(context):
    context._protobuf = ProtobufParser()


@then('it supports a file "{rel}"')
def step_supports(context, rel):
    assert context._protobuf.supports(Path(rel)), f"expected support for {rel}"


@then('it does not support a file "{rel}"')
def step_not_supports(context, rel):
    assert not context._protobuf.supports(Path(rel)), f"unexpected support for {rel}"


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def _cleanup_scenario(context) -> None:
    """Tear down the patched create_app, the spawned server, and the tmp project.

    Called inline at the tail of the only @real_neo4j scenario's last @then so
    the next scenario starts clean. No-op if the scenario didn't allocate a
    server (e.g. the supports()-only smoke scenario).
    """
    original = getattr(context, "_original_create_app", None)
    if original is not None:
        from guru_server import app as server_app

        server_app.create_app = original
        context._original_create_app = None

    server = getattr(context, "server", None)
    if server is not None:
        server.should_exit = True
    thread = getattr(context, "server_thread", None)
    if thread is not None:
        thread.join(timeout=5)
    context.server = None
    context.server_thread = None

    tmp_project = getattr(context, "tmp_project", None)
    if tmp_project is not None:
        with contextlib.suppress(FileNotFoundError):
            (tmp_project / ".guru" / "guru.sock").unlink()
        with contextlib.suppress(FileNotFoundError):
            (tmp_project / ".guru" / "guru.pid").unlink()
        shutil.rmtree(tmp_project, ignore_errors=True)
        context.tmp_project = None
