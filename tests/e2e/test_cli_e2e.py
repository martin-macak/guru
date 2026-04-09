"""End-to-end test: start a real server, use CLI to interact with it.

Marked as 'slow' — skipped by default. Run with:
    uv run pytest -m slow
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embedding import OllamaEmbedder
from guru_server.storage import VectorStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_dir():
    """Create a test project with .guru/, config, and sample markdown files.

    Uses a short path under /tmp to stay within the macOS 104-byte
    AF_UNIX socket path limit.
    """
    import shutil
    import tempfile

    tmp_path = Path(tempfile.mkdtemp(prefix="g_", dir="/tmp"))

    # --- project structure ---
    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    # --- config ---
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

    # --- sample docs ---
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

    yield tmp_path

    import shutil
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture()
def running_server(project_dir):
    """Start a real guru-server on a UDS with a fake embedder, yield, then stop."""

    socket_path = str(project_dir / ".guru" / "guru.sock")
    pid_path = project_dir / ".guru" / "guru.pid"

    # --- fake embedder (deterministic vectors, no Ollama needed) ---
    embedder = OllamaEmbedder()
    _counter = 0

    async def _fake_embed(text: str) -> list[float]:
        nonlocal _counter
        _counter += 1
        vec = [0.01] * 768
        # sprinkle in some variation so search results are differentiated
        vec[_counter % 768] = 1.0
        vec[(_counter * 7) % 768] = 0.5
        return vec

    async def _fake_embed_batch(texts: list[str]) -> list[list[float]]:
        return [await _fake_embed(t) for t in texts]

    embedder.embed = _fake_embed
    embedder.embed_batch = _fake_embed_batch

    # --- real components ---
    config = resolve_config(project_root=project_dir)
    store = VectorStore(db_path=str(project_dir / ".guru" / "db"))

    app = create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(project_dir),
    )

    # --- run uvicorn in a background thread ---
    uvi_config = uvicorn.Config(app, uds=socket_path, log_level="warning")
    server = uvicorn.Server(uvi_config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # write PID so CLI discovery works
    pid_path.write_text(str(os.getpid()))

    # wait for socket to appear
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if Path(socket_path).exists():
            break
        time.sleep(0.1)
    else:
        pytest.fail("guru-server did not start within 10 s")

    yield project_dir

    # --- teardown ---
    server.should_exit = True
    thread.join(timeout=5)
    pid_path.unlink(missing_ok=True)
    Path(socket_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], cwd: Path) -> tuple[int, str]:
    """Invoke the guru CLI in the given working directory.

    We shell out via subprocess so the CLI resolves paths from *cwd*,
    just like a real user would.
    """
    import subprocess

    env = os.environ.copy()
    result = subprocess.run(
        ["uv", "run", "guru", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print(f"CLI FAILED (exit {result.returncode}):\n{output}")
    return result.returncode, output


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestCLIEndToEnd:
    """Full end-to-end: real server on UDS, real CLI subprocess calls."""

    def test_server_status_before_indexing(self, running_server):
        code, out = _run_cli(["server", "status"], cwd=running_server)
        assert code == 0
        assert "server_running" in out
        assert "chunk_count: 0" in out

    def test_index_documents(self, running_server):
        code, out = _run_cli(["index"], cwd=running_server)
        assert code == 0
        assert "Indexed" in out
        assert "chunks" in out
        # Should have found 3 markdown files
        assert "3 documents" in out

    def test_list_after_indexing(self, running_server):
        # index first
        _run_cli(["index"], cwd=running_server)

        code, out = _run_cli(["list"], cwd=running_server)
        assert code == 0
        assert "getting-started.md" in out
        assert "architecture.md" in out
        assert "auth.md" in out

    def test_search(self, running_server):
        _run_cli(["index"], cwd=running_server)

        code, out = _run_cli(["search", "OAuth authentication"], cwd=running_server)
        assert code == 0
        assert "Result" in out
        assert "score" in out

    def test_get_document(self, running_server):
        _run_cli(["index"], cwd=running_server)

        # list to discover exact path
        _, list_out = _run_cli(["list"], cwd=running_server)
        # find the auth.md path
        auth_path = None
        for line in list_out.splitlines():
            if "auth.md" in line:
                auth_path = line.strip().split(" ")[0]
                break
        assert auth_path is not None, f"auth.md not found in list output: {list_out}"

        code, out = _run_cli(["doc", auth_path], cwd=running_server)
        assert code == 0
        assert "Authentication" in out

    def test_server_status_after_indexing(self, running_server):
        _run_cli(["index"], cwd=running_server)

        code, out = _run_cli(["server", "status"], cwd=running_server)
        assert code == 0
        assert "chunk_count" in out
        # chunk_count should be > 0 now
        assert "chunk_count: 0" not in out

    def test_config_shows_rules(self, running_server):
        code, out = _run_cli(["config"], cwd=running_server)
        assert code == 0
        assert "docs" in out
        assert "specs" in out
        assert "documentation" in out
