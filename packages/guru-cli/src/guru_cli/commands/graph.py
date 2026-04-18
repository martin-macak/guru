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

from guru_core.config import resolve_config
from guru_core.discovery import find_guru_root
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    AnnotationNode,
    ArtifactFindQuery,
    ArtifactNeighborsResult,
    ArtifactNode,
    KbLink,
    KbNode,
    OrphanAnnotation,
    QueryResult,
)

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


def _fmt_props(properties: dict[str, _Any]) -> str:
    if not properties:
        return "-"
    return ", ".join(f"{k}={_stringify(v)}" for k, v in properties.items())


def _render_artifact_node_kv(node: ArtifactNode) -> str:
    lines = [
        f"id:          {node.id}",
        f"label:       {node.label}",
        f"properties:  {_fmt_props(node.properties)}",
        f"annotations: {len(node.annotations)}",
        f"links_out:   {len(node.links_out)}",
        f"links_in:    {len(node.links_in)}",
    ]
    return "\n".join(lines)


def _render_neighbors_table(result: ArtifactNeighborsResult, *, truncate: bool) -> str:
    headers = ["ID", "LABEL", "REL_TYPE", "KIND"]
    # Build a quick lookup from node_id -> node for label rendering.
    nodes_by_id: dict[str, ArtifactNode] = {n.id: n for n in result.nodes}
    rows: list[list[str]] = []
    for edge in result.edges:
        # The "neighbor" is whichever endpoint isn't the queried node.
        neighbor_id = edge.to_id if edge.from_id == result.node_id else edge.from_id
        neighbor = nodes_by_id.get(neighbor_id)
        label = neighbor.label if neighbor is not None else "-"
        rows.append([neighbor_id, label, edge.rel_type, edge.kind or "-"])
    if not rows:
        return _format_table(headers, [], truncate=truncate) + "\n(no neighbors)"
    return _format_table(headers, rows, truncate=truncate)


def _render_artifacts_table(nodes: list[ArtifactNode], *, truncate: bool) -> str:
    headers = ["ID", "LABEL", "KB_NAME"]
    rows = [[n.id, n.label, _stringify(n.properties.get("kb_name", "-"))] for n in nodes]
    if not rows:
        return _format_table(headers, [], truncate=truncate) + "\n(no matches)"
    return _format_table(headers, rows, truncate=truncate)


def _render_annotations_table(
    annotations: list[AnnotationNode] | list[OrphanAnnotation],
    *,
    truncate: bool,
    empty_label: str,
) -> str:
    headers = ["ID", "KIND", "AUTHOR", "CREATED", "BODY"]
    rows = [
        [
            a.id,
            a.kind.value,
            a.author,
            _fmt_dt(a.created_at),
            _trunc(a.body.replace("\n", " "), 60),
        ]
        for a in annotations
    ]
    if not rows:
        return _format_table(headers, [], truncate=truncate) + f"\n({empty_label})"
    return _format_table(headers, rows, truncate=truncate)


def _exit_if_graph_disabled() -> None:
    """If the local guru.json sets graph.enabled=false, print and exit 0.

    This is a per-command pre-flight check so that read-only artifact
    subcommands do not even attempt to connect to the daemon when the
    project has explicitly opted out.

    If we cannot determine whether the graph is enabled (e.g. we are not
    inside a guru project), fall through silently — the daemon call will
    fail with the usual "unreachable" error if needed.
    """
    try:
        from pathlib import Path

        root = find_guru_root(Path.cwd())
        cfg = resolve_config(project_root=root)
    except Exception:
        return
    if cfg.graph is not None and cfg.graph.enabled is False:
        click.echo("graph is disabled")
        sys.exit(0)


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


@graph_group.command(name="kb")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit the KbNode as JSON.")
def kb(name: str, as_json: bool) -> None:
    """Show a single KB node."""
    client = _client()
    node = _handle_graph_errors(client.get_kb(name))
    if node is None:
        click.echo(f"KB {name!r} not found", err=True)
        sys.exit(1)
    if as_json:
        click.echo(_json.dumps(node.model_dump(mode="json"), indent=2, default=str))
    else:
        click.echo(_render_kb_kv(node))


@graph_group.command(name="links")
@click.argument("name")
@click.option(
    "--direction",
    type=click.Choice(["in", "out", "both"]),
    default="both",
    help="Which direction of links to list.",
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
    help="Never truncate long values.",
)
def links(name: str, direction: str, as_json: bool, no_truncate: bool) -> None:
    """List a KB's links."""
    client = _client()
    items = _handle_graph_errors(
        client.list_links(name=name, direction=direction),
    )
    if as_json:
        click.echo(
            _json.dumps(
                [link.model_dump(mode="json") for link in items],
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(_render_links_table(items, truncate=not no_truncate))


@graph_group.command(name="query")
@click.argument("cypher", required=False)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the QueryResult as JSON.",
)
def query(cypher: str | None, as_json: bool) -> None:
    """Run a read-only Cypher query.

    The query is forced to read-only on the server — no write flag is
    exposed by the CLI regardless of the Cypher contents.

    Pass the query inline or via stdin:

        guru graph query 'MATCH (k:Kb) RETURN k.name'
        echo 'MATCH (k:Kb) RETURN count(k)' | guru graph query
        guru graph query < query.cypher
    """
    if cypher is None:
        if sys.stdin.isatty():
            click.echo("cypher required (pass as argument or via stdin)")
            raise SystemExit(2)
        cypher = sys.stdin.read()
        if not cypher or not cypher.strip():
            click.echo("cypher required (pass as argument or via stdin)")
            raise SystemExit(2)
    client = _client()
    result = _handle_graph_errors(
        client.query(cypher=cypher, params=None, read_only=True),
    )
    if as_json:
        click.echo(_json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        click.echo(_render_query_result(result))


@graph_group.command(name="describe")
@click.argument("node_id")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the ArtifactNode as JSON.",
)
def describe(node_id: str, as_json: bool) -> None:
    """Show an artifact node, with annotations and links inline."""
    _exit_if_graph_disabled()
    client = _client()
    node = _handle_graph_errors(client.describe_artifact(node_id=node_id))
    if node is None:
        click.echo(f"node {node_id!r} not found", err=True)
        sys.exit(1)
    if as_json:
        click.echo(_json.dumps(node.model_dump(mode="json"), indent=2, default=str))
    else:
        click.echo(_render_artifact_node_kv(node))


@graph_group.command(name="neighbors")
@click.argument("node_id")
@click.option(
    "--direction",
    type=click.Choice(["in", "out", "both"]),
    default="both",
    help="Which direction of edges to walk.",
)
@click.option(
    "--rel-type",
    type=click.Choice(["CONTAINS", "RELATES", "both"]),
    default="both",
    help="Which edge type(s) to include.",
)
@click.option(
    "--kind",
    type=str,
    default=None,
    help="Filter RELATES edges by kind (e.g. imports, calls).",
)
@click.option(
    "--depth",
    type=int,
    default=1,
    help="Maximum hop depth.",
)
@click.option(
    "--limit",
    type=int,
    default=50,
    help="Maximum neighbors to return.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the ArtifactNeighborsResult as JSON.",
)
@click.option(
    "--no-truncate",
    is_flag=True,
    default=False,
    help="Never truncate long values.",
)
def neighbors(
    node_id: str,
    direction: str,
    rel_type: str,
    kind: str | None,
    depth: int,
    limit: int,
    as_json: bool,
    no_truncate: bool,
) -> None:
    """List a node's graph neighbors."""
    _exit_if_graph_disabled()
    client = _client()
    result = _handle_graph_errors(
        client.neighbors(
            node_id=node_id,
            direction=direction,  # type: ignore[arg-type]
            rel_type=rel_type,  # type: ignore[arg-type]
            kind=kind,
            depth=depth,
            limit=limit,
        )
    )
    if as_json:
        click.echo(_json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        click.echo(_render_neighbors_table(result, truncate=not no_truncate))


@graph_group.command(name="find")
@click.option("--name", type=str, default=None, help="Filter by exact name (or qualname).")
@click.option(
    "--qualname-prefix",
    type=str,
    default=None,
    help="Filter by qualified name prefix.",
)
@click.option("--label", type=str, default=None, help="Filter by node label.")
@click.option("--tag", type=str, default=None, help="Filter by tag.")
@click.option("--kb-name", type=str, default=None, help="Filter by KB name.")
@click.option("--limit", type=int, default=50, help="Maximum results.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the matched ArtifactNodes as JSON.",
)
@click.option(
    "--no-truncate",
    is_flag=True,
    default=False,
    help="Never truncate long values.",
)
def find(
    name: str | None,
    qualname_prefix: str | None,
    label: str | None,
    tag: str | None,
    kb_name: str | None,
    limit: int,
    as_json: bool,
    no_truncate: bool,
) -> None:
    """Search for artifacts matching the given filters."""
    _exit_if_graph_disabled()
    client = _client()
    q = ArtifactFindQuery(
        name=name,
        qualname_prefix=qualname_prefix,
        label=label,
        tag=tag,
        kb_name=kb_name,
        limit=limit,
    )
    nodes = _handle_graph_errors(client.find_artifacts(q))
    if as_json:
        click.echo(
            _json.dumps(
                [n.model_dump(mode="json") for n in nodes],
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(_render_artifacts_table(nodes, truncate=not no_truncate))


@graph_group.command(name="annotations")
@click.argument("node_id")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the annotations list as JSON.",
)
@click.option(
    "--no-truncate",
    is_flag=True,
    default=False,
    help="Never truncate long bodies.",
)
def annotations(node_id: str, as_json: bool, no_truncate: bool) -> None:
    """List annotations attached to a node."""
    _exit_if_graph_disabled()
    client = _client()
    node = _handle_graph_errors(client.describe_artifact(node_id=node_id))
    if node is None:
        click.echo(f"node {node_id!r} not found", err=True)
        sys.exit(1)
    if as_json:
        click.echo(
            _json.dumps(
                [a.model_dump(mode="json") for a in node.annotations],
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(
            _render_annotations_table(
                node.annotations,
                truncate=not no_truncate,
                empty_label="no annotations",
            )
        )


@graph_group.command(name="orphans")
@click.option("--limit", type=int, default=50, help="Maximum orphans to list.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the OrphanAnnotation list as JSON.",
)
@click.option(
    "--no-truncate",
    is_flag=True,
    default=False,
    help="Never truncate long bodies.",
)
def orphans(limit: int, as_json: bool, no_truncate: bool) -> None:
    """List orphaned annotations (those whose target node was deleted)."""
    _exit_if_graph_disabled()
    client = _client()
    items = _handle_graph_errors(client.list_orphans(limit=limit))
    if as_json:
        click.echo(
            _json.dumps(
                [o.model_dump(mode="json") for o in items],
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(
            _render_annotations_table(
                items,
                truncate=not no_truncate,
                empty_label="no orphans",
            )
        )
