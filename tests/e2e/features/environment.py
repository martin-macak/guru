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


def _create_project_dir() -> Path:
    """Create a test project with .guru/, config, and sample markdown files.

    Uses a short path under /tmp to stay within the macOS 104-byte
    AF_UNIX socket path limit.
    """
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

    (docs_dir / "getting-started.md").write_text(
        """\
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
"""
    )

    (docs_dir / "architecture.md").write_text(
        """\
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
"""
    )

    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()

    (specs_dir / "auth.md").write_text(
        """\
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
"""
    )

    return tmp_path


def _start_server(project_dir: Path) -> tuple[uvicorn.Server, threading.Thread]:
    """Start a guru-server on UDS with a fake embedder."""

    socket_path = str(project_dir / ".guru" / "guru.sock")
    pid_path = project_dir / ".guru" / "guru.pid"

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


def before_feature(context, feature):
    """Start a fresh server for each feature."""
    context.project_dir = _create_project_dir()
    context.server, context.server_thread = _start_server(context.project_dir)


def after_feature(context, feature):
    """Stop the server and clean up."""
    if hasattr(context, "server"):
        context.server.should_exit = True
        context.server_thread.join(timeout=5)

    if hasattr(context, "project_dir"):
        pid_path = context.project_dir / ".guru" / "guru.pid"
        sock_path = context.project_dir / ".guru" / "guru.sock"
        pid_path.unlink(missing_ok=True)
        sock_path.unlink(missing_ok=True)
        shutil.rmtree(context.project_dir, ignore_errors=True)
