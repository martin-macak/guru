"""`guru graph` — control the optional graph plugin daemon.

Subcommands:
  guru graph start   — spawn the daemon now (blocking until ready)
  guru graph stop    — send SIGTERM to the running daemon
  guru graph status  — show daemon PID, Neo4j status, schema version
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

import click


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
