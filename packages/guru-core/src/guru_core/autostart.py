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


def ensure_server(guru_root: Path, timeout: float = 5.0, log_level: str | None = None) -> None:
    """Ensure the guru server is running."""
    guru_dir = guru_root / ".guru"
    pid_file = guru_dir / "guru.pid"
    sock_file = guru_dir / "guru.sock"

    # Check if already running
    if pid_file.exists() and sock_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if _is_pid_alive(pid):
                return
        except (ValueError, OSError):
            pass

    _cleanup_stale(guru_dir)

    env = os.environ.copy()
    env["GURU_PROJECT_ROOT"] = str(guru_root)

    # Build server command with logging args
    cmd = ["guru-server", "--log-file", str(guru_dir / "server.log")]
    log_level_resolved = log_level or os.environ.get("GURU_LOG_LEVEL")
    if log_level_resolved:
        cmd.extend(["--log-level", log_level_resolved])

    # Redirect stderr to server.log in append mode as safety net for early crashes
    log_path = guru_dir / "server.log"
    log_file = open(log_path, "a")  # noqa: SIM115

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
        start_new_session=True,
        env=env,
    )

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_file.close()
            log_tail = _read_log_tail(log_path)
            raise ServerStartError(f"guru-server exited with code {proc.returncode}.\n{log_tail}")

        if sock_file.exists():
            last_error = _health_check(str(sock_file))
            if last_error is None:
                log_file.close()
                return
        time.sleep(0.1)

    log_file.close()
    log_tail = _read_log_tail(log_path)
    detail = f": {last_error}" if last_error is not None else ""
    raise ServerStartError(f"guru-server did not start within {timeout}s{detail}.\n{log_tail}")


def _read_log_tail(log_path: Path, max_lines: int = 20) -> str:
    """Read the last N lines of the server log for error reporting."""
    try:
        text = log_path.read_text().strip()
        if not text:
            return "Server log is empty."
        lines = text.splitlines()
        tail = lines[-max_lines:]
        return "Server log:\n" + "\n".join(tail)
    except OSError:
        return "Server log not available."


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
