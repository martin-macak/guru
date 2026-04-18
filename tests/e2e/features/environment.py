"""Behave environment hooks — set up and tear down the guru server."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embed_cache import EmbeddingCache
from guru_server.embedding import OllamaEmbedder
from guru_server.federation import FederationRegistry
from guru_server.storage import VectorStore

# ---------------------------------------------------------------------------
# Project directory builders
# ---------------------------------------------------------------------------


def _create_standard_project() -> Path:
    """Project with docs/ and specs/ for the basic CLI feature tests."""
    tmp_path = Path(tempfile.mkdtemp(prefix="g_", dir="/tmp"))

    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    config = {
        "version": 1,
        "rules": [
            {
                "ruleName": "docs",
                "match": {"glob": "docs/**/*.md"},
                "labels": ["documentation"],
            },
            {
                "ruleName": "specs",
                "match": {"glob": "specs/**/*.md"},
                "labels": ["spec"],
            },
        ],
    }
    (tmp_path / ".guru.json").write_text(json.dumps(config, indent=2))

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    (docs_dir / "getting-started.md").write_text("""\
---
title: Getting Started
status: published
---

# Getting Started

Welcome to the project. This guide walks you through initial setup.

## Installation

Install the package with pip:

```bash
pip install guru
```

## Configuration

Create a `guru.json` file in your project root.
""")

    (docs_dir / "architecture.md").write_text("""\
---
title: Architecture Overview
status: approved
---

# Architecture Overview

The system follows a server-centric design.

## Components

There are four main components: core, server, mcp, and cli.

## Data Flow

Data flows from markdown files through the ingestion pipeline into LanceDB.
""")

    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()

    (specs_dir / "auth.md").write_text("""\
---
title: Authentication Spec
status: draft
owner: martin
---

# Authentication

All API access requires authentication.

## OAuth 2.0

External clients use OAuth 2.0 with PKCE flow.

## API Keys

Internal services authenticate via long-lived API keys.
""")

    return tmp_path


def _create_semantic_project() -> Path:
    """Project with topically distinct documents for semantic search tests.

    Three directories, each with a clearly different topic:
    - guides/   -> labeled "guide"
    - references/ -> labeled "reference", "technical"
    - notes/    -> labeled "note"
    """
    tmp_path = Path(tempfile.mkdtemp(prefix="g_", dir="/tmp"))

    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    config = {
        "version": 1,
        "rules": [
            {
                "ruleName": "guides",
                "match": {"glob": "guides/**/*.md"},
                "labels": ["guide"],
            },
            {
                "ruleName": "references",
                "match": {"glob": "references/**/*.md"},
                "labels": ["reference", "technical"],
            },
            {
                "ruleName": "notes",
                "match": {"glob": "notes/**/*.md"},
                "labels": ["note"],
            },
        ],
    }
    (tmp_path / ".guru.json").write_text(json.dumps(config, indent=2))

    # --- guides: cooking ---
    guides_dir = tmp_path / "guides"
    guides_dir.mkdir()

    (guides_dir / "cooking-basics.md").write_text("""\
---
title: Cooking Basics
category: culinary
---

# Cooking Basics

A beginner's guide to cooking delicious meals at home.

## Essential Ingredients

Every kitchen needs olive oil, garlic, onions, salt, pepper, and fresh herbs.
Stock your pantry with rice, pasta, canned tomatoes, and chicken broth.

## Simple Recipes

### Pasta Aglio e Olio

Boil spaghetti. Saute sliced garlic in olive oil until golden. Toss pasta
with the garlic oil, red pepper flakes, and fresh parsley. A classic Italian
recipe ready in 15 minutes.

### Vegetable Stir Fry

Heat sesame oil in a wok. Add sliced bell peppers, broccoli, snap peas, and
carrots. Stir fry on high heat for 3 minutes. Add soy sauce, ginger, and
serve over steamed rice.
""")

    # --- references: databases ---
    refs_dir = tmp_path / "references"
    refs_dir.mkdir()

    (refs_dir / "database-fundamentals.md").write_text("""\
---
title: Database Fundamentals
category: engineering
---

# Database Fundamentals

A reference guide to relational and non-relational database systems.

## SQL Databases

Relational databases store data in tables with rows and columns. Use SQL
to query, insert, update, and delete records. PostgreSQL and MySQL are
the most popular open-source relational database management systems.

### Query Optimization

Use indexes on columns that appear in WHERE clauses. Avoid SELECT * in
production queries. Use EXPLAIN ANALYZE to understand query execution plans.

## NoSQL Databases

Document stores like MongoDB store data as JSON-like documents. Key-value
stores like Redis provide sub-millisecond latency for caching. Column-family
stores like Cassandra handle massive write throughput.
""")

    # --- notes: astronomy ---
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()

    (notes_dir / "solar-system.md").write_text("""\
---
title: Solar System Notes
category: science
---

# The Solar System

Notes on planets, stars, and celestial mechanics.

## The Sun

The Sun is a G-type main-sequence star at the center of our solar system.
It contains 99.86% of the total mass of the solar system. Nuclear fusion
in its core converts hydrogen into helium, producing light and heat.

## Planets

Eight planets orbit the Sun. The inner rocky planets are Mercury, Venus,
Earth, and Mars. The outer gas giants are Jupiter, Saturn, Uranus, and
Neptune. Each planet follows an elliptical orbit governed by gravity.

## Moons and Asteroids

Jupiter has 95 known moons, including the four large Galilean moons:
Io, Europa, Ganymede, and Callisto. The asteroid belt between Mars and
Jupiter contains millions of rocky bodies left over from planet formation.
""")

    return tmp_path


def _create_gitignore_project() -> Path:
    """Project inside a git repo with a gitignored node_modules/ directory.

    Used by the gitignore_discovery BDD feature to verify that
    `git ls-files`-driven discovery skips gitignored content.
    """
    tmp_path = Path(tempfile.mkdtemp(prefix="g_", dir="/tmp"))

    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    config = {
        "version": 1,
        "rules": [
            {
                "ruleName": "all",
                "match": {"glob": "**/*.md"},
                "labels": ["documentation"],
            },
        ],
    }
    (tmp_path / ".guru.json").write_text(json.dumps(config, indent=2))

    # Real markdown (not gitignored) — should be indexed
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "real.md").write_text("""\
---
title: Real Document
---

# Real Document

This file lives in docs/ and is tracked by git.
It should appear in the index after `guru index`.
""")

    # "Generated" markdown inside a gitignored directory — must NOT be indexed
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "README.md").write_text("""\
# Generated README

This file lives in a gitignored directory and must not be indexed.
""")

    # .gitignore excludes node_modules and .guru runtime state
    (tmp_path / ".gitignore").write_text("node_modules/\n.guru/\n")

    # Initialize a git repo so `git ls-files` works
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "add", "docs/", ".gitignore", ".guru.json"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, check=True)

    return tmp_path


# ---------------------------------------------------------------------------
# Server helpers
# ---------------------------------------------------------------------------


def _make_fake_embedder() -> OllamaEmbedder:
    """Return an OllamaEmbedder with mocked embed methods."""
    embedder = OllamaEmbedder()
    _counter = 0

    async def _fake_embed(text: str) -> list[float]:
        nonlocal _counter
        _counter += 1
        vec = [0.01] * 768
        vec[_counter % 768] = 1.0
        vec[(_counter * 7) % 768] = 0.5
        return vec

    async def _fake_embed_batch(texts: list[str]) -> list[list[float]]:
        return [await _fake_embed(t) for t in texts]

    embedder.embed = _fake_embed
    embedder.embed_batch = _fake_embed_batch

    async def _fake_check_health() -> None:
        pass

    embedder.check_health = _fake_check_health
    return embedder


def _start_server(
    project_dir: Path, embedder: OllamaEmbedder
) -> tuple[uvicorn.Server, threading.Thread]:
    """Start a guru-server on UDS."""
    socket_path = str(project_dir / ".guru" / "guru.sock")
    pid_path = project_dir / ".guru" / "guru.pid"

    config = resolve_config(project_root=project_dir)
    store = VectorStore(db_path=str(project_dir / ".guru" / "db"))

    # Create an isolated embedding cache for this feature
    cache_path = os.environ.get("GURU_EMBED_CACHE_PATH")
    embed_cache = EmbeddingCache(db_path=Path(cache_path)) if cache_path else None

    app = create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(project_dir),
        auto_index=False,
        embed_cache=embed_cache,
    )

    uvi_config = uvicorn.Config(app, uds=socket_path, log_level="warning")
    server = uvicorn.Server(uvi_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    pid_path.write_text(str(os.getpid()))

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if Path(socket_path).exists():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("guru-server did not start within 10 s")

    return server, thread


def _create_federation_project(name: str, base_dir: Path, fed_dir: Path) -> Path:
    """Create a minimal guru project for federation tests.

    Writes a .guru.json with a name field, a .guru/db/ directory,
    and a few sample docs.  Returns the project root Path.
    """
    project_dir = base_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)

    guru_dir = project_dir / ".guru"
    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    config = {
        "version": 1,
        "name": name,
        "rules": [
            {
                "ruleName": "docs",
                "match": {"glob": "docs/**/*.md"},
                "labels": ["documentation"],
            },
        ],
    }
    (project_dir / ".guru.json").write_text(json.dumps(config, indent=2))

    docs_dir = project_dir / "docs"
    docs_dir.mkdir()

    (docs_dir / "overview.md").write_text(f"""\
---
title: {name.capitalize()} Overview
---

# {name.capitalize()} Overview

This is the overview document for the {name} server.

## Summary

The {name} server provides federated search capabilities and indexes documentation.
""")

    (docs_dir / "guide.md").write_text(f"""\
---
title: {name.capitalize()} Guide
---

# {name.capitalize()} Guide

This guide explains how to use the {name} server.

## Getting Started

Connect to the {name} server using the federation protocol.
""")

    return project_dir


def _start_federation_server(
    project_dir: Path,
    embedder: OllamaEmbedder,
    fed_dir: Path,
) -> tuple[uvicorn.Server, threading.Thread, FederationRegistry]:
    """Start a guru server in a thread and register it in the federation directory.

    Returns (server, thread, registry).
    """
    socket_path = str(project_dir / ".guru" / "guru.sock")
    pid_path = project_dir / ".guru" / "guru.pid"

    config = resolve_config(project_root=project_dir)
    store = VectorStore(db_path=str(project_dir / ".guru" / "db"))

    cache_path = os.environ.get("GURU_EMBED_CACHE_PATH")
    embed_cache = EmbeddingCache(db_path=Path(cache_path)) if cache_path else None

    app = create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(project_dir),
        auto_index=False,
        embed_cache=embed_cache,
    )

    uvi_config = uvicorn.Config(app, uds=socket_path, log_level="warning")
    server = uvicorn.Server(uvi_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    pid = os.getpid()
    pid_path.write_text(str(pid))

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if Path(socket_path).exists():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError(f"guru-server for {project_dir.name} did not start within 10 s")

    # Read project name from .guru.json (fall back to directory name)
    try:
        cfg_data = json.loads((project_dir / ".guru.json").read_text())
        server_name = cfg_data.get("name", project_dir.name)
    except Exception:
        server_name = project_dir.name

    registry = FederationRegistry(
        name=server_name,
        pid=pid,
        socket_path=socket_path,
        project_root=str(project_dir),
        federation_dir=fed_dir,
    )
    registry.register()

    return server, thread, registry


def _wait_for_index(project_dir: Path, timeout: float = 30.0) -> None:
    """Poll the server status until no job is running."""
    import httpx

    socket_path = str(project_dir / ".guru" / "guru.sock")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            transport = httpx.HTTPTransport(uds=socket_path)
            with httpx.Client(transport=transport, timeout=5.0) as client:
                resp = client.get("http://localhost/status")
                data = resp.json()
                if data.get("current_job") is None:
                    return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError("Index did not complete within timeout")


def _trigger_and_wait_index(project_dir: Path, timeout: float = 30.0) -> dict:
    """Trigger indexing via REST and wait for completion. Returns the job detail."""
    import httpx

    socket_path = str(project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        resp = client.post("http://localhost/index", json={})
        job_data = resp.json()
        job_id = job_data["job_id"]

    # Wait for completion
    _wait_for_index(project_dir, timeout)

    # Get final job detail
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        resp = client.get(f"http://localhost/jobs/{job_id}")
        return resp.json()


# ---------------------------------------------------------------------------
# Behave hooks
# ---------------------------------------------------------------------------


def before_scenario(context, scenario):
    """Auto-skip scenarios that are specified but rely on later-PR machinery.

    Scenarios tagged with `@skip_until_prN` document future behavior and are
    intentionally under-implemented at this point in the plan. We mark them
    skipped here so behave treats them as skipped rather than erroring on
    undefined steps.
    """
    for tag in scenario.tags:
        if tag.startswith("skip_until_"):
            scenario.skip(f"pending: {tag}")
            return


def before_feature(context, feature):
    """Start a fresh server for each feature.

    Tags decide which project fixture is used:
    - @real_ollama → semantic project with real Ollama embeddings
    - @gitignore_project → git-repo project with gitignored files
    - @federation → federation tests; no default server is started
    - (default) → standard project with mocked embedder

    The artifact_indexing and graph_optional features use the polyglot fixture
    and drive server startup from their own step definitions (via
    `Given graph is enabled/disabled`), so we only set up the embedding cache
    and @real_neo4j skip logic here.
    """
    # artifact_indexing / graph_optional scenarios copy the polyglot fixture
    # from a Background step and start their own server. We just need to
    # isolate the embedding cache and auto-skip @real_neo4j when the env
    # doesn't provide a Neo4j.
    if "artifact_indexing" in feature.filename or "graph_optional" in feature.filename:
        cache_fd, cache_name = tempfile.mkstemp(prefix="guru-test-cache-", suffix=".db")
        os.close(cache_fd)
        os.environ["GURU_EMBED_CACHE_PATH"] = cache_name
        context._cache_path = cache_name
        context._polyglot_managed = True

        # Isolate graph daemon state — matches the graph_plugin hook so the
        # @real_neo4j subset doesn't collide with other features' daemons.
        context.graph_tmp = tempfile.mkdtemp(prefix="guru-graph-art-")
        context.guru_tmp_cfg = tempfile.mkdtemp(prefix="guru-art-cfg-")
        os.environ["XDG_CONFIG_HOME"] = context.guru_tmp_cfg
        os.environ["XDG_DATA_HOME"] = os.path.join(context.graph_tmp, "data")
        os.environ["XDG_STATE_HOME"] = os.path.join(context.graph_tmp, "state")
        os.environ["XDG_RUNTIME_DIR"] = os.path.join(context.graph_tmp, "run")
        os.environ["GURU_GRAPH_HOME"] = os.path.join(context.graph_tmp, "home")

        if "real_neo4j" in feature.tags and os.environ.get("GURU_REAL_NEO4J") != "1":
            feature.skip("GURU_REAL_NEO4J=1 not set")
            return
        for scenario in feature.scenarios:
            if "real_neo4j" in scenario.tags and os.environ.get("GURU_REAL_NEO4J") != "1":
                scenario.skip("GURU_REAL_NEO4J=1 not set")
        return

    # Graph plugin scenarios are self-contained — they use GraphClient or a
    # FakeBackend directly rather than needing a default guru-server startup.
    # Skip the normal server-bootstrap path.
    # annotations_and_curation + orphan_triage follow the same pattern: only
    # guru-graph daemon needed, seeded via submit_parse_result.
    if (
        "graph_plugin" in feature.filename
        or "graph_cli_reads" in feature.filename
        or "annotations_and_curation" in feature.filename
        or "orphan_triage" in feature.filename
    ):
        import os as _os
        import tempfile as _tempfile

        context.graph_tmp = _tempfile.mkdtemp(prefix="guru-graph-e2e-")
        context.guru_tmp_cfg = _tempfile.mkdtemp(prefix="guru-e2e-cfg-")
        _os.environ["XDG_CONFIG_HOME"] = context.guru_tmp_cfg
        # Isolate all platformdirs dirs so the daemon and Neo4j state land
        # inside the temp directory, never touching real user directories.
        _os.environ["XDG_DATA_HOME"] = _os.path.join(context.graph_tmp, "data")
        _os.environ["XDG_STATE_HOME"] = _os.path.join(context.graph_tmp, "state")
        _os.environ["XDG_RUNTIME_DIR"] = _os.path.join(context.graph_tmp, "run")
        # Override platform-specific default (e.g. macOS Library/Application
        # Support) with a single writable directory so local BDD works even
        # when the platform default isn't writable under the test sandbox.
        _os.environ["GURU_GRAPH_HOME"] = _os.path.join(context.graph_tmp, "home")

        # Auto-skip @real_neo4j scenarios unless GURU_REAL_NEO4J=1.
        if "real_neo4j" in feature.tags and _os.environ.get("GURU_REAL_NEO4J") != "1":
            feature.skip("GURU_REAL_NEO4J=1 not set")
            return
        for scenario in feature.scenarios:
            if "real_neo4j" in scenario.tags and _os.environ.get("GURU_REAL_NEO4J") != "1":
                scenario.skip("GURU_REAL_NEO4J=1 not set")
        return

    # Isolate the embedding cache per feature so scenarios don't pollute each other
    cache_fd, cache_name = tempfile.mkstemp(prefix="guru-test-cache-", suffix=".db")
    os.close(cache_fd)
    os.environ["GURU_EMBED_CACHE_PATH"] = cache_name
    context._cache_path = cache_name

    if "federation" in feature.tags:
        # Federation tests manage their own servers via step definitions.
        # Create a shared federation directory and a shared embedder.
        # Short paths under /tmp — macOS caps AF_UNIX paths at 104 bytes, and
        # the default TMPDIR (/var/folders/…) alone eats ~53 of those.
        context.fed_dir = Path(tempfile.mkdtemp(prefix="g_fed_", dir="/tmp"))
        context.fed_base_dir = Path(tempfile.mkdtemp(prefix="g_fedp_", dir="/tmp"))
        context.embedder = _make_fake_embedder()
        context.servers = {}
        context.registries = {}
        context.fed_project_dirs = {}
        return

    if "real_ollama" in feature.tags:
        context.project_dir = _create_semantic_project()
        context.embedder = OllamaEmbedder()  # real Ollama
    elif "gitignore_project" in feature.tags:
        context.project_dir = _create_gitignore_project()
        context.embedder = _make_fake_embedder()
    else:
        context.project_dir = _create_standard_project()
        context.embedder = _make_fake_embedder()

    context.server, context.server_thread = _start_server(context.project_dir, context.embedder)


def after_feature(context, feature):
    """Stop the server and clean up."""
    if getattr(context, "_polyglot_managed", False):
        import contextlib as _ctx
        import os as _os
        import shutil as _shutil

        # Stop any guru-server the steps started.
        if hasattr(context, "server") and context.server is not None:
            context.server.should_exit = True
        if hasattr(context, "server_thread") and context.server_thread is not None:
            context.server_thread.join(timeout=5)

        # Remove the per-feature project tmpdir (copied from fixtures/).
        project_dir = getattr(context, "project_dir", None)
        if project_dir is not None:
            pid_path = project_dir / ".guru" / "guru.pid"
            sock_path = project_dir / ".guru" / "guru.sock"
            with _ctx.suppress(FileNotFoundError):
                pid_path.unlink()
            with _ctx.suppress(FileNotFoundError):
                sock_path.unlink()
            _shutil.rmtree(project_dir, ignore_errors=True)

        polyglot_tmp_root = getattr(context, "_polyglot_tmp_root", None)
        if polyglot_tmp_root is not None:
            _shutil.rmtree(polyglot_tmp_root, ignore_errors=True)

        # Kill any daemon we (or auto-start) spawned.
        with _ctx.suppress(Exception):
            from guru_graph.config import GraphPaths as _GP
            from guru_graph.lifecycle import read_pid_file as _rpf

            paths = _GP.default()
            pid = _rpf(paths.pid_file)
            if pid:
                with _ctx.suppress(ProcessLookupError):
                    _os.kill(pid, 15)

        for attr in ("graph_tmp", "guru_tmp_cfg"):
            d = getattr(context, attr, None)
            if d:
                _shutil.rmtree(d, ignore_errors=True)
        for key in (
            "GURU_GRAPH_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "XDG_RUNTIME_DIR",
            "XDG_CONFIG_HOME",
        ):
            _os.environ.pop(key, None)

        # Clean up the isolated embedding cache
        cache_path = getattr(context, "_cache_path", None)
        if cache_path and os.path.exists(cache_path):
            os.unlink(cache_path)
        os.environ.pop("GURU_EMBED_CACHE_PATH", None)
        return

    if (
        "graph_plugin" in feature.filename
        or "graph_cli_reads" in feature.filename
        or "annotations_and_curation" in feature.filename
        or "orphan_triage" in feature.filename
    ):
        import contextlib as _ctx
        import os as _os
        import shutil as _shutil

        # Kill any daemon we started so the next feature run isn't blocked.
        with _ctx.suppress(Exception):
            from guru_graph.config import GraphPaths as _GP
            from guru_graph.lifecycle import read_pid_file as _rpf

            paths = _GP.default()
            pid = _rpf(paths.pid_file)
            if pid:
                with _ctx.suppress(ProcessLookupError):
                    _os.kill(pid, 15)
        for attr in ("graph_tmp", "guru_tmp_cfg"):
            d = getattr(context, attr, None)
            if d:
                _shutil.rmtree(d, ignore_errors=True)
        for key in (
            "GURU_GRAPH_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "XDG_RUNTIME_DIR",
            "XDG_CONFIG_HOME",
        ):
            _os.environ.pop(key, None)
        return

    if hasattr(context, "_mcp_patcher"):
        context._mcp_patcher.stop()

    if hasattr(context, "server"):
        context.server.should_exit = True
        context.server_thread.join(timeout=5)

    if hasattr(context, "project_dir"):
        pid_path = context.project_dir / ".guru" / "guru.pid"
        sock_path = context.project_dir / ".guru" / "guru.sock"
        pid_path.unlink(missing_ok=True)
        sock_path.unlink(missing_ok=True)
        shutil.rmtree(context.project_dir, ignore_errors=True)

    # Federation-specific cleanup
    if hasattr(context, "servers"):
        for _name, (srv, thr) in context.servers.items():
            srv.should_exit = True
            thr.join(timeout=5)

    if hasattr(context, "registries"):
        for _name, registry in context.registries.items():
            registry.deregister()

    if hasattr(context, "fed_project_dirs"):
        for project_path in context.fed_project_dirs.values():
            shutil.rmtree(project_path, ignore_errors=True)

    if hasattr(context, "fed_base_dir"):
        shutil.rmtree(context.fed_base_dir, ignore_errors=True)

    if hasattr(context, "fed_dir"):
        shutil.rmtree(context.fed_dir, ignore_errors=True)

    # Clean up the isolated embedding cache
    cache_path = getattr(context, "_cache_path", None)
    if cache_path and os.path.exists(cache_path):
        os.unlink(cache_path)
    os.environ.pop("GURU_EMBED_CACHE_PATH", None)
