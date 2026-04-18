# guru-graph

Optional graph plugin for Guru. FastAPI-over-UDS daemon that owns a Neo4j
Community subprocess and exposes a domain-shaped KB graph API plus a Cypher
escape hatch.

The daemon is lazy-spawned by guru-server on first graph call. It runs in
one of two modes:

- **Subprocess mode** (default): `guru-graph` spawns and owns a Neo4j
  Community subprocess. Requires Java 21+ on `PATH`.
- **Connect-only mode**: when `GURU_NEO4J_BOLT_URI` is set, the daemon
  connects to an externally-managed Neo4j (Docker, shared cluster, CI
  service). No Neo4j subprocess is spawned.

The graph is **enabled by default**; opt OUT by setting
`graph.enabled: false` in `.guru.json` or
`~/.config/guru/config.json`. Graph failures never propagate to end users —
`guru-server` swallows `GraphUnavailable` so search and indexing keep
working in degraded mode.

See `docs/superpowers/specs/2026-04-17-graph-plugin-design.md` for the
daemon design and
`docs/superpowers/specs/2026-04-18-artifact-graph-knowledge-base-design.md`
for the artifact-graph schema layered on top.
