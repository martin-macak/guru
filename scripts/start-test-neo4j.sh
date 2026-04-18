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
from pathlib import Path

from guru_graph.neo4j_process import start_neo4j
from guru_graph.preflight import check_java_installed, check_neo4j_installed

port = int(os.environ["PORT"])
base = Path(os.environ["BASE"])
pid_file = base / "neo4j.pid"

if pid_file.exists():
    try:
        os.killpg(int(pid_file.read_text(encoding="utf-8").strip()), signal.SIGTERM)
    except (ProcessLookupError, ValueError):
        pass

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
