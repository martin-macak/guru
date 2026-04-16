from __future__ import annotations

import contextlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


class FederationRegistry:
    """Manages federation discovery file I/O, peer list, and maintenance.

    Each guru server writes a discovery file on startup and removes it
    on shutdown. The maintenance sweep cleans up files from crashed peers.
    """

    def __init__(
        self,
        name: str,
        pid: int,
        socket_path: str,
        project_root: str,
        federation_dir: Path,
    ):
        self.name = name
        self.pid = pid
        self.socket_path = socket_path
        self.project_root = project_root
        self.federation_dir = federation_dir
        self._discovery_file = federation_dir / f"{name}.json"

    def register(self) -> None:
        """Write discovery file atomically. Creates federation dir if needed."""
        self.federation_dir.mkdir(parents=True, exist_ok=True)

        if self._discovery_file.exists():
            try:
                existing = json.loads(self._discovery_file.read_text())
                existing_pid = existing.get("pid")
                existing_socket = existing.get("socket")
                # Warn when an alive server with a different socket already holds this name.
                # We check the socket path to distinguish a genuine collision from a simple
                # re-registration of this exact server instance.
                if (
                    existing_pid
                    and existing_socket != self.socket_path
                    and _is_pid_alive(existing_pid)
                ):
                    logger.warning(
                        "Federation name collision: overwriting '%s' "
                        "(existing PID %d is still alive)",
                        self.name,
                        existing_pid,
                    )
            except (json.JSONDecodeError, OSError):
                pass

        data = {
            "name": self.name,
            "pid": self.pid,
            "socket": self.socket_path,
            "project_root": self.project_root,
            "started_at": datetime.now(UTC).isoformat(),
        }

        tmp_path = self.federation_dir / f"{self.name}.tmp.{self.pid}"
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.rename(self._discovery_file)

    def deregister(self) -> None:
        """Remove own discovery file. Idempotent."""
        with contextlib.suppress(FileNotFoundError):
            self._discovery_file.unlink()

    def list_peers(self) -> list[dict]:
        """Return list of live peers, excluding self."""
        peers = []
        if not self.federation_dir.exists():
            return peers

        for path in self.federation_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.debug("Skipping unreadable discovery file: %s", path)
                continue

            if data.get("name") == self.name:
                continue

            pid = data.get("pid")
            if pid is None or not _is_pid_alive(pid):
                continue

            peers.append(data)

        return peers

    def sweep(self) -> None:
        """Maintenance sweep: remove discovery files for dead peers."""
        if not self.federation_dir.exists():
            return

        for path in self.federation_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            pid = data.get("pid")
            if pid is None or not _is_pid_alive(pid):
                try:
                    path.unlink()
                    logger.info("Removed stale discovery file: %s (PID %s)", path.name, pid)
                except FileNotFoundError:
                    pass
