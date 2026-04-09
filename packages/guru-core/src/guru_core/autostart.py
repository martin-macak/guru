from __future__ import annotations

import os
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

    # Wait for socket to appear, then verify server is healthy via GET /status
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if sock_file.exists():
            last_error = _health_check(str(sock_file))
            if last_error is None:
                return
        time.sleep(0.1)

    detail = f": {last_error}" if last_error is not None else ""
    raise ServerStartError(
        f"guru-server did not start within {timeout}s{detail}. "
        f"Check server logs or run `guru server start` manually."
    )


def _health_check(sock_path: str) -> Exception | None:
    """Perform a GET /status health check over the Unix domain socket.

    Returns None on success, or the exception on failure.
    """
    import httpx  # local import to avoid circular deps

    try:
        transport = httpx.HTTPTransport(uds=sock_path)
        with httpx.Client(transport=transport) as client:
            resp = client.get("http://localhost/status")
            resp.raise_for_status()
        return None
    except Exception as exc:
        return exc
