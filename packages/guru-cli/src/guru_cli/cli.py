from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from guru_core.discovery import find_guru_root, GuruNotFoundError
from guru_core.autostart import ensure_server
from guru_core.client import GuruClient
from guru_core.types import Rule, MatchConfig


DEFAULT_CONFIG = [
    {"ruleName": "default", "match": {"glob": "**/*.md"}},
]


def _get_client() -> GuruClient:
    """Find guru root and return a connected client."""
    try:
        guru_root = find_guru_root(Path.cwd())
    except GuruNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    ensure_server(guru_root)
    return GuruClient(guru_root=guru_root)


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx):
    """Guru CLI — local knowledge base manager."""
    if ctx.invoked_subcommand is None:
        # Bare `guru` launches TUI (Phase 3)
        click.echo("TUI is planned for Phase 3. Use `guru --help` for available commands.")


@cli.command()
def tui():
    """Launch the Guru TUI (planned for Phase 3)."""
    click.echo("TUI is planned for Phase 3. Use `guru --help` for available commands.")


@cli.command()
def init():
    """Initialize a guru project in the current directory."""
    guru_dir = Path.cwd() / ".guru"
    guru_json = Path.cwd() / "guru.json"

    if guru_dir.is_dir():
        click.echo("Already initialized — .guru/ directory exists.")
        return

    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    if not guru_json.exists():
        guru_json.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")

    click.echo(f"Initialized guru project in {Path.cwd()}")


@cli.group()
def server():
    """Manage the guru server."""


@server.command("start")
def server_start():
    """Start the guru server."""
    try:
        guru_root = find_guru_root(Path.cwd())
    except GuruNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    ensure_server(guru_root)
    click.echo("Server is running.")


@server.command("stop")
def server_stop():
    """Stop the guru server."""
    import os
    import signal

    try:
        guru_root = find_guru_root(Path.cwd())
    except GuruNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    pid_file = guru_root / ".guru" / "guru.pid"
    if not pid_file.exists():
        click.echo("Server is not running.")
        return

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo("Server stopped.")
    except ProcessLookupError:
        click.echo("Server was not running (stale PID).")
        pid_file.unlink(missing_ok=True)


@server.command("status")
def server_status():
    """Show server status."""
    client = _get_client()
    status = _run(client.status())
    for key, value in status.items():
        click.echo(f"  {key}: {value}")


@cli.command()
@click.argument("path", required=False)
def index(path):
    """Index documents in the knowledge base."""
    client = _get_client()
    result = _run(client.trigger_index(path))
    click.echo(f"Indexed {result['indexed']} chunks from {result['documents']} documents.")


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results")
def search(query, limit):
    """Search the knowledge base."""
    client = _get_client()
    results = _run(client.search(query, n_results=limit))
    if not results:
        click.echo("No results found.")
        return
    for i, r in enumerate(results, 1):
        click.echo(f"\n--- Result {i} (score: {r.get('score', 'N/A')}) ---")
        click.echo(f"File: {r['file_path']}")
        click.echo(f"Section: {r.get('header_breadcrumb', 'N/A')}")
        click.echo(r["content"][:200])


@cli.command()
@click.argument("file_path")
@click.option("--section", "-s", default=None, help="Header breadcrumb path")
def doc(file_path, section):
    """Get a document or section from the knowledge base."""
    client = _get_client()
    if section:
        result = _run(client.get_section(file_path, section))
    else:
        result = _run(client.get_document(file_path))
    click.echo(json.dumps(result, indent=2))


@cli.command("list")
def list_docs():
    """List documents in the knowledge base."""
    client = _get_client()
    docs = _run(client.list_documents())
    if not docs:
        click.echo("No documents indexed.")
        return
    for d in docs:
        click.echo(f"  {d['file_path']} ({d.get('chunk_count', '?')} chunks)")


@cli.command()
def config():
    """Show resolved configuration with provenance."""
    # Read config files directly — no server dependency needed
    from guru_core.types import Rule

    guru_root = Path.cwd()
    try:
        guru_root = find_guru_root(Path.cwd())
    except GuruNotFoundError:
        pass

    sources = []

    # Check global config
    global_path = Path.home() / ".config" / "guru" / "config.json"
    if global_path.is_file():
        rules = json.loads(global_path.read_text())
        for r in rules:
            sources.append({"source": str(global_path), **r})

    # Check local config (guru.json preferred, then .guru/config.json)
    local_path = guru_root / "guru.json"
    if not local_path.is_file():
        local_path = guru_root / ".guru" / "config.json"
    if local_path.is_file():
        rules = json.loads(local_path.read_text())
        for r in rules:
            sources.append({"source": str(local_path), **r})

    if not sources:
        sources = [{"source": "default", "ruleName": "default", "match": {"glob": "**/*.md"}}]

    click.echo(json.dumps(sources, indent=2))
