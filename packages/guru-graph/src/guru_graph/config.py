"""Platform paths and utility helpers.

Storage layout (see spec §Architecture):
  macOS: ~/Library/Application Support/guru/graph/
  Linux: $XDG_DATA_HOME/guru/graph/  (data)
         $XDG_STATE_HOME/guru/graph/ (pid, lock, log, socket fallback)
"""

from __future__ import annotations

import socket
import sys
from dataclasses import dataclass
from pathlib import Path

import platformdirs


@dataclass(frozen=True)
class GraphPaths:
    socket: Path
    data_dir: Path
    pid_file: Path
    lock_file: Path
    log_file: Path

    @classmethod
    def default(cls) -> GraphPaths:
        if sys.platform == "darwin":
            base = Path(platformdirs.user_data_dir("guru", appauthor=False)) / "graph"
            sock = Path(platformdirs.user_data_dir("guru", appauthor=False)) / "graph.sock"
            return cls(
                socket=sock,
                data_dir=base / "neo4j",
                pid_file=base / "daemon.pid",
                lock_file=base / ".daemon.lock",
                log_file=base / "daemon.log",
            )
        # Linux / other POSIX: split data vs state per XDG
        data = Path(platformdirs.user_data_dir("guru", appauthor=False)) / "graph"
        state = Path(platformdirs.user_state_dir("guru", appauthor=False)) / "graph"
        runtime = Path(platformdirs.user_runtime_dir("guru", appauthor=False) or state)
        return cls(
            socket=runtime / "graph.sock",
            data_dir=data / "neo4j",
            pid_file=state / "daemon.pid",
            lock_file=state / ".daemon.lock",
            log_file=state / "daemon.log",
        )

    @classmethod
    def for_test(cls, *, base: Path) -> GraphPaths:
        return cls(
            socket=base / "graph.sock",
            data_dir=base / "neo4j",
            pid_file=base / "daemon.pid",
            lock_file=base / ".daemon.lock",
            log_file=base / "daemon.log",
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.socket.parent.mkdir(parents=True, exist_ok=True)


def allocate_free_loopback_port() -> int:
    """Bind to 127.0.0.1:0 and return the OS-assigned port.

    TOCTOU caveat: another process could grab the port between this call and
    the Neo4j subprocess binding. In practice, Neo4j starts quickly and we
    fall back to one retry in the lifecycle path if the port was stolen.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()
