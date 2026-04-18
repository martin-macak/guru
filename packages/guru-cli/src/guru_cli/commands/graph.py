"""`guru graph` — control the optional graph plugin daemon.

Subcommands:
  guru graph start   — spawn the daemon now (blocking until ready)
  guru graph stop    — send SIGTERM to the running daemon
  guru graph status  — show daemon PID, Neo4j status, schema version
"""

from __future__ import annotations

import asyncio
import contextlib
import json as _json
import os
import shutil as _shutil
import signal
import sys
from datetime import datetime as _datetime
from typing import Any as _Any

import click

from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import KbLink, KbNode, QueryResult

_ELLIPSIS = "\u2026"  # …


def _fmt_dt(d: _datetime | None) -> str:
    if d is None:
        return "-"
    return d.isoformat(timespec="seconds").replace("+00:00", "Z")


def _trunc(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    if width <= 1:
        return _ELLIPSIS
    return s[: width - 1] + _ELLIPSIS


def _term_width() -> int:
    try:
        return _shutil.get_terminal_size().columns
    except OSError:
        return 100


def _format_table(headers: list[str], rows: list[list[str]], *, truncate: bool) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if len(cell) > widths[i]:
                widths[i] = len(cell)

    if truncate:
        # Reserve 2 spaces between columns. If total > terminal width, shrink
        # widest columns (down to the header length floor).
        tw = _term_width()
        separators = 2 * (len(headers) - 1)
        total = sum(widths) + separators
        if total > tw:
            floors = [len(h) for h in headers]
            over = total - tw
            while over > 0:
                idx = widths.index(max(widths))
                if widths[idx] <= floors[idx] + 1:
                    break
                widths[idx] -= 1
                over -= 1

    def fmt_row(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            c = _trunc(cell, widths[i]) if truncate else cell
            parts.append(c.ljust(widths[i]))
        return "  ".join(parts).rstrip()

    lines = [fmt_row(headers)]
    for row in rows:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def _render_kbs_table(kbs: list[KbNode], *, truncate: bool) -> str:
    headers = ["NAME", "PROJECT ROOT", "TAGS", "UPDATED"]
    rows = [
        [
            k.name,
            k.project_root,
            ", ".join(k.tags) if k.tags else "-",
            _fmt_dt(k.updated_at),
        ]
        for k in kbs
    ]
    if not rows:
        return _format_table(headers, [], truncate=truncate) + "\n(no KBs)"
    return _format_table(headers, rows, truncate=truncate)


def _render_kb_kv(kb: KbNode) -> str:
    lines = [
        f"name:         {kb.name}",
        f"project_root: {kb.project_root}",
        f"tags:         {', '.join(kb.tags) if kb.tags else '-'}",
        f"created_at:   {_fmt_dt(kb.created_at)}",
        f"updated_at:   {_fmt_dt(kb.updated_at)}",
        f"last_seen_at: {_fmt_dt(kb.last_seen_at)}",
    ]
    if kb.metadata:
        lines.append("metadata:")
        key_w = max(len(k) for k in kb.metadata)
        for k, v in kb.metadata.items():
            lines.append(f"  {k.ljust(key_w)}  {v}")
    else:
        lines.append("metadata:     -")
    return "\n".join(lines)


def _render_links_table(links: list[KbLink], *, truncate: bool) -> str:
    headers = ["FROM", "KIND", "TO", "CREATED"]
    rows = [
        [link.from_kb, link.kind.value, link.to_kb, _fmt_dt(link.created_at)] for link in links
    ]
    if not rows:
        return _format_table(headers, [], truncate=truncate) + "\n(no links)"
    return _format_table(headers, rows, truncate=truncate)


def _render_query_result(r: QueryResult) -> str:
    if not r.rows:
        return f"(no rows)  elapsed: {r.elapsed_ms:.1f} ms"
    headers = list(r.columns) if r.columns else [f"col{i}" for i in range(len(r.rows[0]))]
    rows = [[_stringify(c) for c in row] for row in r.rows]
    tbl = _format_table(headers, rows, truncate=True)
    return f"{tbl}\nelapsed: {r.elapsed_ms:.1f} ms"


def _stringify(value: _Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, dict | list):
        return _json.dumps(value, default=str)
    return str(value)


def _client():
    """Construct a GraphClient pointed at the default socket.

    Exits with code 2 if the guru-graph package isn't installed — matches
    the existing ``guru graph status`` behaviour.
    """
    try:
        from guru_core.graph_client import GraphClient
        from guru_graph.config import GraphPaths
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        sys.exit(2)
    paths = GraphPaths.default()
    return GraphClient(socket_path=str(paths.socket), auto_start=False)


def _handle_graph_errors(coro):
    """Run *coro* and translate GraphUnavailable into click's exit 1.

    Other exceptions propagate — unexpected failures should show a traceback
    so bugs are visible.
    """
    try:
        return asyncio.run(coro)
    except GraphUnavailable as e:
        click.echo(f"daemon: unreachable ({e})", err=True)
        sys.exit(1)


@click.group(name="graph")
def graph_group() -> None:
    """Control the optional graph plugin daemon."""


@graph_group.command(name="start")
def start() -> None:
    """Start the graph daemon and block until its socket is ready."""
    try:
        from guru_graph.config import GraphPaths
        from guru_graph.lifecycle import connect_or_spawn
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        sys.exit(2)
    paths = GraphPaths.default()
    click.echo(f"starting daemon; socket={paths.socket}")
    connect_or_spawn(paths=paths, ready_timeout_seconds=60.0)
    click.echo("daemon ready")


@graph_group.command(name="stop")
def stop() -> None:
    """Send SIGTERM to the running graph daemon."""
    try:
        from guru_graph.config import GraphPaths
        from guru_graph.lifecycle import read_pid_file
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        sys.exit(2)
    paths = GraphPaths.default()
    pid = read_pid_file(paths.pid_file)
    if pid is None:
        click.echo("no daemon running")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"sent SIGTERM to daemon pid={pid}")
    except ProcessLookupError:
        click.echo("daemon pid recorded but process missing; cleaning up")
        with contextlib.suppress(FileNotFoundError):
            paths.pid_file.unlink()


@graph_group.command(name="status")
def status() -> None:
    """Print graph daemon status."""
    try:
        from guru_core.graph_client import GraphClient
        from guru_graph.config import GraphPaths
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        sys.exit(2)
    paths = GraphPaths.default()
    client = GraphClient(socket_path=str(paths.socket), auto_start=False)
    try:
        info = asyncio.run(client.version())
        health = asyncio.run(client.health())
        click.echo("daemon: reachable")
        click.echo(f"protocol: {info.protocol_version}")
        click.echo(f"backend:  {info.backend} {info.backend_version}")
        click.echo(f"schema:   {info.schema_version}")
        click.echo(f"status:   {health.status}")
    except Exception as e:
        click.echo(f"daemon: unreachable ({e})")
        sys.exit(1)


@graph_group.command(name="kbs")
@click.option(
    "--prefix",
    type=str,
    default=None,
    help="Filter KBs whose name starts with this prefix.",
)
@click.option(
    "--tag",
    type=str,
    default=None,
    help="Filter KBs that carry this tag.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit JSON array instead of a text table.",
)
@click.option(
    "--no-truncate",
    is_flag=True,
    default=False,
    help="Never truncate long paths.",
)
def kbs(prefix: str | None, tag: str | None, as_json: bool, no_truncate: bool) -> None:
    """List all KB nodes in the graph."""
    client = _client()
    nodes = _handle_graph_errors(client.list_kbs(prefix=prefix, tag=tag))
    if as_json:
        click.echo(
            _json.dumps(
                [n.model_dump(mode="json") for n in nodes],
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(_render_kbs_table(nodes, truncate=not no_truncate))
