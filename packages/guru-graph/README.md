# guru-graph

Optional graph plugin for Guru. FastAPI-over-UDS daemon that supervises a
Neo4j Community subprocess and exposes a domain-shaped KB graph API plus a
Cypher escape hatch.

The daemon entry point is `guru-graph-daemon`; it's lazy-spawned by
guru-server on first graph call. It runs in one of two modes:

- **Subprocess mode** (default): the daemon execs the `neo4j` binary it
  finds on `PATH`. Requires both **Java 17+** and **Neo4j 5.x** to be
  installed by the user — neither is bundled with guru. On macOS:
  `brew install openjdk@17 neo4j`. On Debian/Ubuntu:
  `apt install openjdk-17-jre neo4j`. Other platforms: see
  https://neo4j.com/download/.
- **Connect-only mode**: when `GURU_NEO4J_BOLT_URI` is set (e.g.
  `bolt://127.0.0.1:7687`), the daemon connects to an externally-managed
  Neo4j (Docker, shared cluster, CI service). No Neo4j subprocess is
  spawned, and both Java and Neo4j preflight checks are skipped — no local
  install needed.

The graph is **enabled by default**; opt OUT by setting
`graph.enabled: false` in `.guru.json` or `~/.config/guru/config.json`.
Graph failures never propagate to end users — `guru-server` swallows
`GraphUnavailable` so search and indexing keep working in degraded mode
even if Java or Neo4j aren't installed.

See `docs/superpowers/specs/2026-04-17-graph-plugin-design.md` for the
daemon design and
`docs/superpowers/specs/2026-04-18-artifact-graph-knowledge-base-design.md`
for the artifact-graph schema layered on top.
