from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


class ServerStartError(RuntimeError):
    pass


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _cleanup_stale(guru_dir: Path) -> None:
    """Remove stale socket and pid files."""
    (guru_dir / "guru.sock").unlink(missing_ok=True)
    (guru_dir / "guru.pid").unlink(missing_ok=True)


def ensure_server(guru_root: Path, timeout: float = 5.0) -> None:
    """Ensure the guru server is running.

    If the server is running (valid PID, socket exists), return immediately.
    If stale state is detected, clean up and restart.
    If no server is running, start one.
    """
    guru_dir = guru_root / ".guru"
    pid_file = guru_dir / "guru.pid"
    sock_file = guru_dir / "guru.sock"

    # Check if already running
    if pid_file.exists() and sock_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if _is_pid_alive(pid):
                return  # Server is running
        except (ValueError, OSError):
            pass

    # Clean up stale state
    _cleanup_stale(guru_dir)

    # Start server
    env = os.environ.copy()
    env["GURU_PROJECT_ROOT"] = str(guru_root)

    subprocess.Popen(
        ["guru-server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )

    # Wait for socket to appear
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if sock_file.exists():
            return
        time.sleep(0.1)

    raise ServerStartError(
        f"guru-server did not start within {timeout}s. "
        f"Check server logs or run `guru server start` manually."
    )
