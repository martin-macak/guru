from __future__ import annotations

import asyncio
import contextlib
import json
import re
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

import click

from guru_core.autostart import ensure_server
from guru_core.client import GuruClient
from guru_core.discovery import GuruNotFoundError, find_guru_root

DEFAULT_CONFIG = {
    "version": 1,
    "rules": [
        {"ruleName": "default", "match": {"glob": "**/*.md"}},
    ],
}


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


def _parse_duration_to_ms(text: str) -> int:
    """Parse a duration like '30d', '2w', '6h', '15m' into milliseconds."""
    match = re.fullmatch(r"(\d+)([dwhm])", text)
    if match is None:
        raise click.BadParameter(f"Invalid duration '{text}'. Use forms like 30d, 2w, 6h, 15m.")
    n = int(match.group(1))
    unit = match.group(2)
    multipliers = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
    }
    return n * multipliers[unit]


@click.group(invoke_without_command=True)
@click.version_option(version=pkg_version("guru-cli"))
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
    cwd = Path.cwd()
    guru_dir = cwd / ".guru"
    dot_guru_json = cwd / ".guru.json"
    guru_json = cwd / "guru.json"
    mcp_json = cwd / ".mcp.json"
    gitignore = cwd / ".gitignore"

    # 1. Create .guru/ directory
    if guru_dir.is_dir():
        click.echo("Already initialized — .guru/ directory exists.")
    else:
        guru_dir.mkdir()
        (guru_dir / "db").mkdir()
        click.echo("Created .guru/")

    # 2. Create .guru.json (preferred dotfile); warn if legacy guru.json exists
    if dot_guru_json.exists():
        click.echo(".guru.json already exists, skipping.")
    else:
        dot_guru_json.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
        click.echo("Created .guru.json with default rules")

    if guru_json.exists():
        click.echo(
            "Warning: legacy guru.json found. "
            "Consider renaming it to .guru.json (dotfile convention)."
        )

    # 3. Merge guru into .mcp.json
    _init_mcp_json(mcp_json)

    # 4. Add .guru/ to .gitignore
    _init_gitignore(gitignore)

    # 5. Install the agent-facing skill
    from guru_cli.skills_install import install_skill

    try:
        guru_version = pkg_version("guru-cli")
    except Exception:
        guru_version = "0.0.0"
    try:
        installed = install_skill(cwd, guru_version=guru_version)
    except Exception as e:
        click.echo(f"Warning: skill install failed: {e}", err=True)
    else:
        click.echo(f"Installed skill: .claude/skills/guru-knowledge-base ({len(installed)} files)")


def _init_mcp_json(mcp_json: Path) -> None:
    """Add guru entry to .mcp.json, creating or merging as needed."""
    guru_entry = {"command": "guru-mcp"}

    if mcp_json.exists():
        mcp = json.loads(mcp_json.read_text())
        servers = mcp.setdefault("mcpServers", {})
        if "guru" in servers:
            click.echo("guru already configured in .mcp.json, skipping.")
            return
        servers["guru"] = guru_entry
    else:
        mcp = {"mcpServers": {"guru": guru_entry}}

    mcp_json.write_text(json.dumps(mcp, indent=2) + "\n")
    click.echo("Added guru to .mcp.json")


def _init_gitignore(gitignore: Path) -> None:
    """Add .guru/ to .gitignore if not already present."""
    marker = ".guru/"
    if gitignore.exists():
        content = gitignore.read_text()
        if marker in content.splitlines():
            click.echo(".guru/ already in .gitignore, skipping.")
            return
        if not content.endswith("\n"):
            content += "\n"
        content += marker + "\n"
    else:
        content = marker + "\n"

    gitignore.write_text(content)
    click.echo("Added .guru/ to .gitignore")


@cli.group()
def server():
    """Manage the guru server."""


@server.command("start")
@click.option("--foreground", is_flag=True, help="Run in foreground (no daemonization)")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Log level",
)
@click.option("--log-file", type=click.Path(), default=None, help="Log file path")
def server_start(foreground, log_level, log_file):
    """Start the guru server."""
    try:
        guru_root = find_guru_root(Path.cwd())
    except GuruNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    if foreground:
        _run_foreground(guru_root, log_level=log_level, log_file=log_file)
    else:
        ensure_server(guru_root, log_level=log_level, log_file=log_file)
        click.echo("Server is running.")


def _run_foreground(guru_root: Path, log_level: str | None = None, log_file: str | None = None):
    """Run the server in the current process (foreground mode)."""
    import os

    os.environ["GURU_PROJECT_ROOT"] = str(guru_root)

    argv = []
    if log_level:
        argv.extend(["--log-level", log_level])
    if log_file:
        argv.extend(["--log-file", log_file])

    from guru_server.main import main as server_main

    server_main(argv=argv)


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
@click.option("--job", "job_id", default=None, help="Show details for a specific job")
def server_status(job_id):
    """Show server status."""
    client = _get_client()
    if job_id:
        job = _run(client.get_job(job_id))
        for key, value in job.items():
            click.echo(f"  {key}: {value}")
        return
    status = _run(client.status())
    current_job = status.pop("current_job", None)
    cache_block = status.pop("cache", None)
    for key, value in status.items():
        click.echo(f"  {key}: {value}")
    if current_job:
        total = current_job["files_total"]
        processed = current_job["files_processed"]
        skipped = current_job["files_skipped"]
        click.echo(f"  Indexing: {processed}/{total} files processed ({skipped} skipped)")
    if cache_block:
        click.echo("")
        click.echo(f"Cache: {cache_block['path']}")
        click.echo(f"  Entries:       {cache_block['total_entries']:,}")
        size_mb = cache_block["total_bytes"] / (1024 * 1024)
        click.echo(f"  Size:          {size_mb:.1f} MB")
        if cache_block["by_model"]:
            models_line = ", ".join(
                f"{m} ({c})" for m, c in sorted(cache_block["by_model"].items())
            )
            click.echo(f"  Models:        {models_line}")
        if cache_block.get("last_job_hit_rate") is not None:
            rate = cache_block["last_job_hit_rate"] * 100
            click.echo(
                f"  Last job:      {cache_block['last_job_hits']} hits / "
                f"{cache_block['last_job_misses']} misses ({rate:.1f}%)"
            )


@cli.command()
def index():
    """Index documents in the knowledge base."""
    client = _get_client()
    result = _run(client.trigger_index())
    click.echo(f"Indexing started (job {result['job_id']})")


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
    from guru_core.config import DEFAULT_RULES, load_config, merge_rules

    guru_root = Path.cwd()
    with contextlib.suppress(GuruNotFoundError):
        guru_root = find_guru_root(Path.cwd())

    global_path = Path.home() / ".config" / "guru" / "config.json"
    local_path = guru_root / ".guru.json"
    if not local_path.is_file():
        local_path = guru_root / "guru.json"
    if not local_path.is_file():
        local_path = guru_root / ".guru" / "config.json"

    global_cfg = load_config(global_path)
    local_cfg = load_config(local_path)

    # Determine source labels before merging
    rule_source: dict[str, str] = {}
    if global_cfg:
        for r in global_cfg.rules:
            rule_source[r.rule_name] = str(global_path)
    if local_cfg:
        for r in local_cfg.rules:
            rule_source[r.rule_name] = str(local_path)  # local overrides global

    # Apply the same merge semantics as the server
    if global_cfg is None and local_cfg is None:
        effective = list(DEFAULT_RULES)
        for r in effective:
            rule_source[r.rule_name] = "default"
    elif global_cfg is None:
        effective = local_cfg.rules
    elif local_cfg is None:
        effective = global_cfg.rules
    else:
        effective = merge_rules(global_cfg.rules, local_cfg.rules)

    output = []
    for rule in effective:
        entry = json.loads(rule.model_dump_json(by_alias=True))
        entry["source"] = rule_source.get(rule.rule_name, "default")
        output.append(entry)

    click.echo(json.dumps(output, indent=2))


@cli.group()
def cache():
    """Manage the embedding cache."""


@cache.command("info")
def cache_info():
    """Show cache size, entry count, and model breakdown."""
    client = _get_client()
    stats = _run(client.cache_info())
    click.echo(f"  path:          {stats['path']}")
    click.echo(f"  total entries: {stats['total_entries']}")
    size_mb = stats["total_bytes"] / (1024 * 1024)
    click.echo(f"  total size:    {size_mb:.2f} MB")
    if stats["by_model"]:
        click.echo("  by model:")
        for model, count in sorted(stats["by_model"].items()):
            click.echo(f"    {model}: {count}")
    if stats.get("last_job_hit_rate") is not None:
        rate = stats["last_job_hit_rate"] * 100
        click.echo(
            f"  last job:      {stats['last_job_hits']} hits / "
            f"{stats['last_job_misses']} misses ({rate:.1f}%)"
        )


@cache.command("clear")
@click.option("--model", default=None, help="Only clear entries for this model")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def cache_clear(model, yes):
    """Delete cache entries. Defaults to everything; --model scopes to one model."""
    if not yes:
        click.confirm("Delete cache entries?", abort=True)
    client = _get_client()
    result = _run(client.cache_clear(model=model))
    click.echo(f"Deleted {result['deleted']} entries")


@cache.command("prune")
@click.option(
    "--older-than",
    "older_than",
    required=True,
    help="Delete entries not accessed in this duration (e.g. 30d, 2w, 6h, 15m)",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def cache_prune(older_than, yes):
    """Delete entries with accessed_at older than the given duration."""
    older_than_ms = _parse_duration_to_ms(older_than)
    if not yes:
        click.confirm("Prune cache entries?", abort=True)
    client = _get_client()
    result = _run(client.cache_prune(older_than_ms=older_than_ms))
    click.echo(f"Pruned {result['deleted']} entries")


from guru_cli.commands.graph import graph_group  # noqa: E402

cli.add_command(graph_group)

from guru_cli.commands.update import update_cmd  # noqa: E402

cli.add_command(update_cmd)
