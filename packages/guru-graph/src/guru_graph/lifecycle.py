"""Daemon lazy-start, flock-based leader election, stale-socket recovery.

This module is imported by BOTH the guru-core GraphClient (to autostart) and
the guru-graph daemon entrypoint (to write pid/lock).
"""

from __future__ import annotations

import contextlib
import fcntl
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .config import GraphPaths

logger = logging.getLogger(__name__)


class DaemonNotReady(RuntimeError):
    pass


def read_pid_file(path: Path) -> int | None:
    try:
        text = path.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def write_pid_file(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{pid}")
    tmp.write_text(str(pid))
    os.replace(tmp, path)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def is_socket_alive(path: Path) -> bool:
    """Probe whether the UDS socket has a listener accepting connections."""
    if not path.exists():
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(str(path))
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False
    finally:
        s.close()


def _spawn_daemon() -> int:
    """Spawn the guru-graph daemon detached and return its pid.

    Tests monkeypatch this function; production calls it once the flock is
    held and the socket is confirmed dead.
    """
    proc = subprocess.Popen(
        [sys.executable, "-m", "guru_graph.main"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid


def connect_or_spawn(*, paths: GraphPaths, ready_timeout_seconds: float = 30.0) -> None:
    """Ensure a daemon is running and its socket is reachable.

    1. Probe socket. If alive → done.
    2. flock on .daemon.lock (blocking). Re-probe — another peer may have
       won the race.
    3. Clean stale socket/pid if present; spawn a fresh daemon.
    4. Poll until socket is reachable or timeout.
    """
    if is_socket_alive(paths.socket):
        return
    paths.ensure_dirs()
    lock_fd = os.open(paths.lock_file, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if is_socket_alive(paths.socket):
            return
        if paths.socket.exists():
            with contextlib.suppress(FileNotFoundError):
                paths.socket.unlink()
        existing = read_pid_file(paths.pid_file)
        if existing is not None and not _pid_alive(existing):
            with contextlib.suppress(FileNotFoundError):
                paths.pid_file.unlink()

        pid = _spawn_daemon()
        write_pid_file(paths.pid_file, pid)

        deadline = time.monotonic() + ready_timeout_seconds
        while time.monotonic() < deadline:
            if is_socket_alive(paths.socket):
                return
            time.sleep(0.2)
        raise DaemonNotReady(f"daemon did not bind {paths.socket} within {ready_timeout_seconds}s")
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
