#!/usr/bin/env bash
# Spin up an ephemeral Neo4j 5.x container on the local machine for running
# @real_neo4j tests without installing Neo4j natively.
#
# Usage:
#   ./scripts/start-test-neo4j.sh
#   export GURU_NEO4J_BOLT_URI="bolt://127.0.0.1:${PORT:-17687}"
#   GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/ -v
set -euo pipefail

PORT=${PORT:-17687}
NAME=${NAME:-guru-graph-test-neo4j}

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  -p "$PORT:7687" \
  -e NEO4J_AUTH=none \
  -e NEO4J_PLUGINS='[]' \
  neo4j:5 >/dev/null

echo "waiting for neo4j on bolt://127.0.0.1:$PORT..."
for _ in $(seq 1 60); do
  if docker exec "$NAME" cypher-shell "RETURN 1" >/dev/null 2>&1; then
    echo "ready (bolt://127.0.0.1:$PORT)"
    echo ""
    echo "To run @real_neo4j tests against this container:"
    echo "  export GURU_NEO4J_BOLT_URI=\"bolt://127.0.0.1:$PORT\""
    echo "  GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/ -v"
    exit 0
  fi
  sleep 1
done
echo "neo4j did not become ready" >&2
exit 1
