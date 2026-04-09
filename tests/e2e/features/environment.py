"""Behave environment hooks — set up and tear down the guru server."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embedding import OllamaEmbedder
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

    config = [
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
    ]
    (tmp_path / "guru.json").write_text(json.dumps(config, indent=2))

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

    config = [
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
    ]
    (tmp_path / "guru.json").write_text(json.dumps(config, indent=2))

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
    return embedder


def _start_server(
    project_dir: Path, embedder: OllamaEmbedder
) -> tuple[uvicorn.Server, threading.Thread]:
    """Start a guru-server on UDS."""
    socket_path = str(project_dir / ".guru" / "guru.sock")
    pid_path = project_dir / ".guru" / "guru.pid"

    config = resolve_config(project_root=project_dir)
    store = VectorStore(db_path=str(project_dir / ".guru" / "db"))

    app = create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(project_dir),
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


# ---------------------------------------------------------------------------
# Behave hooks
# ---------------------------------------------------------------------------


def before_feature(context, feature):
    """Start a fresh server for each feature.

    Features tagged @real_ollama get real Ollama embeddings and the
    semantic project layout. All others get the standard project with
    a mocked embedder.
    """
    if "real_ollama" in feature.tags:
        context.project_dir = _create_semantic_project()
        context.embedder = OllamaEmbedder()  # real Ollama
    else:
        context.project_dir = _create_standard_project()
        context.embedder = _make_fake_embedder()

    context.server, context.server_thread = _start_server(context.project_dir, context.embedder)


def after_feature(context, feature):
    """Stop the server and clean up."""
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
