from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from guru_core.discovery import find_guru_root, GuruNotFoundError
from guru_core.autostart import ensure_server
from guru_core.client import GuruClient


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
    from guru_core.config import load_rules, merge_rules, DEFAULT_RULES

    guru_root = Path.cwd()
    try:
        guru_root = find_guru_root(Path.cwd())
    except GuruNotFoundError:
        pass

    global_path = Path.home() / ".config" / "guru" / "config.json"
    local_path = guru_root / "guru.json"
    if not local_path.is_file():
        local_path = guru_root / ".guru" / "config.json"

    global_rules = load_rules(global_path)
    local_rules = load_rules(local_path)

    # Determine source labels before merging
    rule_source: dict[str, str] = {}
    if global_rules:
        for r in global_rules:
            rule_source[r.rule_name] = str(global_path)
    if local_rules:
        for r in local_rules:
            rule_source[r.rule_name] = str(local_path)  # local overrides global

    # Apply the same merge semantics as the server
    if global_rules is None and local_rules is None:
        effective = list(DEFAULT_RULES)
        for r in effective:
            rule_source[r.rule_name] = "default"
    elif global_rules is None:
        effective = local_rules
    elif local_rules is None:
        effective = global_rules
    else:
        effective = merge_rules(global_rules, local_rules)

    output = []
    for rule in effective:
        entry = json.loads(rule.model_dump_json(by_alias=True))
        entry["source"] = rule_source.get(rule.rule_name, "default")
        output.append(entry)

    click.echo(json.dumps(output, indent=2))
