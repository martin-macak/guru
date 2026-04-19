#!/usr/bin/env bash
# Spin up an ephemeral native Neo4j on the local machine for running
# @real_neo4j tests without Docker.
#
# Usage:
#   ./scripts/start-test-neo4j.sh
#   export GURU_NEO4J_BOLT_URI="bolt://127.0.0.1:${PORT:-17687}"
#   GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/ -v
set -euo pipefail

PORT=${PORT:-17687}
BASE=${BASE:-/tmp/guru-graph-test-neo4j}
export PORT BASE

uv run python - <<'PY'
from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path

from guru_graph.neo4j_process import start_neo4j
from guru_graph.preflight import check_java_installed, check_neo4j_installed


def _process_looks_like_neo4j(pid: int) -> bool:
    """Return True if the process identified by *pid* looks like a neo4j/java process."""
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        if cmdline_path.exists():
            # /proc/<pid>/cmdline stores argv entries separated by null bytes.
            cmdline = (
                cmdline_path.read_text(encoding="utf-8", errors="ignore")
                .replace("\x00", " ")
                .lower()
            )
            return "neo4j" in cmdline or "java" in cmdline
    except OSError:
        pass
    try:
        cmdline = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip().lower()
    except (OSError, subprocess.SubprocessError):
        return False
    return "neo4j" in cmdline or "java" in cmdline


def _cleanup_existing_neo4j(pid_path: Path) -> None:
    """Terminate the previously-started neo4j process group recorded in *pid_path*."""
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    try:
        if not _process_looks_like_neo4j(pid):
            return
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


port = int(os.environ["PORT"])
base = Path(os.environ["BASE"])
pid_file = base / "neo4j.pid"

if pid_file.exists():
    _cleanup_existing_neo4j(pid_file)

shutil.rmtree(base, ignore_errors=True)
base.mkdir(parents=True, exist_ok=True)

check_java_installed()
check_neo4j_installed()
runtime = start_neo4j(
    data_dir=base / "data",
    bolt_port=port,
    log_file=base / "neo4j.log",
)
pid_file.write_text(str(runtime.process.pid), encoding="utf-8")

print(f"ready ({runtime.bolt_uri})")
print("")
print("To run @real_neo4j tests against this local Neo4j:")
print(f'  export GURU_NEO4J_BOLT_URI="{runtime.bolt_uri}"')
print("  GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/ -v")
print("")
print("To stop it later:")
print(f"  kill -TERM -- -$(cat {pid_file})")
PY
