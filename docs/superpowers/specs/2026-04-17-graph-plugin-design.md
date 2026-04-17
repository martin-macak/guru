# Graph Plugin — Federated Artifact Graph Infrastructure

**Date:** 2026-04-17
**Status:** Draft

---

## Problem

Guru indexes documents per-project into LanceDB, but it has no way to model *relationships between artifacts* — which documents reference which, which KBs depend on which, which OpenAPI endpoint is defined in which file, which class inherits from which. Vector similarity answers "what is this like?" but not "what does this connect to?". A federated knowledge-graph layer complements the vector index and unlocks graph-aware retrieval (e.g. neighbourhood expansion, dependency traversal, structural queries) as a future feature.

This spec establishes the **infrastructure only**. Artifact-level modelling (files, classes, methods, OpenAPI endpoints via tree-sitter) is explicitly out of scope and will follow once the plumbing is proven.

## Goals

1. Add an **optional** graph plugin to Guru, packaged as a workspace peer to the other packages.
2. Stand up a **single machine-wide graph** shared across all Guru projects on the developer's machine.
3. Deliver a **domain-shaped API** (not raw Cypher) for KB CRUD and KB-to-KB links, plus a `/query` Cypher escape hatch for power-user experimentation.
4. Use **Neo4j Community Edition** as the initial backend, behind a clean abstraction that permits swapping to any other openCypher DB later without touching consumers.
5. Provide **protocol versioning and forward-compat guarantees** so client/server upgrades are safe.
6. Guarantee that when the graph is disabled, unreachable, or failing, **guru-server continues to function with reduced accuracy** — never propagate graph failures to the end user.
7. Ship BDD feature files as part of the spec; every MVP scenario is covered.

## Non-Goals

- **Not** shipping any artifact-level modelling. No file, class, method, endpoint nodes in MVP.
- **Not** tree-sitter integration. Reserved for a follow-up spec.
- **Not** per-project graph namespacing. Names are machine-global.
- **Not** multi-machine graph replication or sync.
- **Not** hot backup, clustering, or RBAC (Neo4j Community doesn't offer these, and we don't need them).
- **Not** auto-installing Neo4j or the JRE. Preflight detects + instructs, same pattern as Ollama.
- **Not** exposing graph operations via MCP (yet). MCP integration is a follow-up once artifact nodes exist and the agent-facing query surface is meaningful.
- **Not** data import/export tools in v1. Endpoints reserved; implementation deferred to v1.1.

---

## Architecture

A new workspace package joins the monorepo:

```
packages/
  guru-core/    (existing)
  guru-server/  (existing)
  guru-mcp/     (existing)
  guru-cli/     (existing)
  guru-graph/   (NEW — FastAPI-over-UDS daemon + Neo4j backend)
```

### Dependency graph

```
guru-cli    -> guru-core
guru-mcp    -> guru-core
guru-server -> guru-core
guru-graph  -> guru-core

guru-server -> guru-graph         (RUNTIME ONLY, over UDS via guru-core.GraphClient)
```

`guru-server` never imports `guru_graph` Python symbols. The runtime dependency is transport-only — an HTTP-over-UDS call through a client living in `guru-core`. The compile-time dependency graph stays:

```
guru-cli    -> guru-core
guru-mcp    -> guru-core
guru-server -> guru-core
guru-graph  -> guru-core
guru-core   -> httpx
```

### Runtime topology (machine-wide)

```
guru-server (proj-A)  ─┐
guru-server (proj-B)  ─┼──► guru-graph daemon ──► Neo4j Community (JVM subprocess)
guru-server (proj-C)  ─┘       (FastAPI/UDS)         (Bolt on 127.0.0.1:<port>)
```

- Exactly one `guru-graph` daemon per machine when enabled. All `guru-server` instances share it.
- `guru-graph` is the sole owner of the Neo4j subprocess lifecycle. Clients **never** talk to Bolt directly.
- One shared graph at the machine level; `(:Kb)` nodes for every KB seen on this machine.

### Storage paths

| Artifact | Path (macOS) | Path (Linux) |
|---|---|---|
| UDS socket | `~/Library/Application Support/guru/graph.sock` | `$XDG_RUNTIME_DIR/guru/graph.sock` (fallback: `$XDG_STATE_HOME/guru/graph.sock`) |
| Neo4j data | `~/Library/Application Support/guru/graph/neo4j/` | `$XDG_DATA_HOME/guru/graph/neo4j/` |
| Daemon PID | `~/Library/Application Support/guru/graph/daemon.pid` | `$XDG_STATE_HOME/guru/graph/daemon.pid` |
| Daemon lock | `~/Library/Application Support/guru/graph/.daemon.lock` | `$XDG_STATE_HOME/guru/graph/.daemon.lock` |
| Daemon log | `~/Library/Application Support/guru/graph/daemon.log` | `$XDG_STATE_HOME/guru/graph/daemon.log` |
| Neo4j log | inside the Neo4j data dir (`neo4j.log`) | inside the Neo4j data dir |

macOS AF_UNIX paths stay under the 104-byte limit; `~/Library/Application Support/guru/graph.sock` is well within it.

### Constitution amendments

Two amendments to `ARCHITECTURE.md` are required:

1. **Scope the "single-owner-of-state" rule to per-project state.**
   *Current:* "guru-server is the single process that owns all state."
   *Amended:* "guru-server owns all **per-project** state. Machine-wide shared services (e.g. the graph plugin) are owned by their dedicated daemons."

2. **Permit one loopback TCP port for the graph backend.**
   *Current:* "No TCP ports. No firewall prompts. No port collisions between projects."
   *Amended:* "No TCP ports are used for inter-component communication. **Exception:** third-party backends (currently Neo4j) may bind to a loopback-only TCP port; `guru-graph` is responsible for picking a free port dynamically, recording it in state, and restricting exposure to `127.0.0.1`. Bolt traffic never leaves the graph daemon's process boundary."

---

## Process lifecycle & optionality

### Config gating (opt-in, off by default)

Global config `~/.config/guru/config.json` gains a new top-level `graph` object:

```json
{
  "version": 1,
  "rules": [...],
  "graph": { "enabled": true }
}
```

- Default: `enabled: false` (or `graph` key absent).
- No per-project override in MVP. Machine-wide on/off only.
- `guru-server` only constructs a `GraphClient` when `graph.enabled == true`. When disabled, all graph-dependent code paths skip silently.

### Preflight (on `guru-graph` daemon startup, mirrors `guru-server`'s Ollama pattern)

1. `java -version` → must report ≥ 17. Hard error with install instructions otherwise.
2. `neo4j --version` → must report ≥ 5.x. Hard error otherwise.
3. Storage paths writable.

Hard-error messages follow the existing style in `packages/guru-server/src/guru_server/startup.py`:

> *Neo4j is not installed or not on PATH. Install it with: `brew install neo4j` (macOS) or follow https://neo4j.com/download/. Requires Java 17+.*

### Lazy start with race-safe leader election

When a `guru-server` wants to talk to the graph:

1. Try `connect()` to `graph.sock`.
2. If ECONNREFUSED or ENOENT:
   1. Acquire `flock()` on `.daemon.lock` (blocking, 30 s timeout).
   2. Re-check the socket — another process may have started the daemon during the wait. If yes: release lock, connect, done.
   3. Else: spawn `guru-graph-daemon` as a detached child (double-fork; new session; stdio redirected to `daemon.log`). Write daemon PID to `daemon.pid` atomically.
   4. Poll socket readiness up to 30 s.
   5. Release lock.
3. If the daemon exists but does not respond → treat as corrupt: `kill -0` probe, clean up stale socket/PID, then restart via step 2.

Both `guru-graph` and `neo4j` are lazy-started and stay running indefinitely for MVP — no idle timeout. An idle-timeout mechanism is future work (v1.1+). Stopping mid-indexing is harmful; the optimisation isn't worth getting wrong in MVP.

### Cold-start mitigation

Neo4j JVM warmup is 15–30 s on first invocation. First-graph-operation latency will be high. Accepted as a known limitation for MVP. A convenience CLI command is provided:

- `guru graph start` — spawn the daemon now (blocking until ready); intended for shell profile / boot-time warm-up.
- `guru graph status` — show daemon PID, Neo4j PID, protocol/schema versions, reachability.
- `guru graph stop` — signal SIGTERM to the daemon (graceful).

These are CLI conveniences only; guru-server itself never requires a pre-warmed daemon.

### Shutdown & failure modes

- **Daemon SIGTERM** → stop accepting new requests → graceful shutdown of Neo4j → exit.
- **Neo4j crashes under the daemon** → daemon logs the crash, attempts **one** restart with a 5 s delay. If the retry also fails → daemon enters "unhealthy" state; new requests return `503` with body `{"error":"graph_unavailable","detail":"<reason>","log":"<path>"}`; existing guru-server clients translate this to `GraphUnavailable`.
- **Daemon itself crashes** → next `guru-server` operation lazy-restarts via the leader-election path. Stale socket/PID cleaned up.
- **Host reboot** → everything gone; Neo4j journals its own store; next lazy-start rehydrates.

### Graceful degradation in guru-server

Graph is a strictly optional augmentation. Contract:

- `graph.enabled == false` → `guru-server` never constructs a `GraphClient` at all.
- Daemon unreachable / 503 / protocol mismatch → `GraphClient` methods raise `GraphUnavailable`.
- Every `guru-server` call site that uses graph wraps it in a `graph_or_skip(coro)` helper that logs once per process and returns a sentinel. Features degrade silently, never propagate to the end user.
- `GET /status` on `guru-server` exposes `graph_enabled: bool` and `graph_reachable: bool`. CLI/TUI render a "graph: off" or "graph: degraded" indicator.

---

## Interface design, backend abstraction, escape hatch

### Layered architecture inside `guru-graph`

```
  HTTP/UDS routes (FastAPI + Pydantic)     ← wire protocol, validation
  Domain services                          ← business ops, translate to Cypher
  GraphBackend (Protocol)                  ← Cypher-execution abstraction
  Neo4jBackend (concrete)                  ← Neo4j Python driver over Bolt
```

### Why Cypher is the abstraction seam

The backend exposes **Cypher execution** and **transactions**, not domain methods. Domain logic (`upsert_kb`, `link_kbs`, etc.) lives in the service layer above, which translates calls into Cypher. Rationale:

- Every future backend (Memgraph, LadybugDB, FalkorDB) can implement the backend in one class — just wire `execute` / `execute_read` / `transaction` to the new driver.
- Domain logic stays in one place, not duplicated per backend.
- A non-Cypher backend (Cozo, etc.) would need a Cypher-to-X translator — strictly opt-in future work.

### `GraphBackend` protocol

`packages/guru-graph/guru_graph/backend/base.py`:

```python
class GraphBackend(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def health(self) -> BackendHealth: ...
    def info(self) -> BackendInfo: ...                  # name, version, schema_version
    def execute(self, cypher: str, params: dict) -> CypherResult: ...
    def execute_read(self, cypher: str, params: dict) -> CypherResult: ...
    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[Tx]: ...
    def ensure_schema(self, target_version: int) -> None: ...
```

### Backend registry (open-closed)

```python
GraphBackendRegistry.register("neo4j", Neo4jBackend)
```

Adding a backend later = one `register()` call + one class. No touch to domain services or routes.

### HTTP API surface (FastAPI over UDS)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/kbs` | upsert KB node (idempotent on `name`) |
| `GET` | `/kbs` | list KBs (optional `?prefix=`, `?tag=`) |
| `GET` | `/kbs/{name}` | get one |
| `DELETE` | `/kbs/{name}` | delete KB and its edges |
| `POST` | `/kbs/{name}/links` | create a link to another KB |
| `DELETE` | `/kbs/{name}/links/{to}/{kind}` | remove one link |
| `GET` | `/kbs/{name}/links?direction=in\|out\|both` | list links |
| `POST` | `/query` | raw Cypher escape hatch |
| `GET` | `/health` | reachability + backend liveness |
| `GET` | `/version` | protocol + backend + schema version |

All request/response bodies are typed Pydantic models. Per the constitution, shared Pydantic models live in `guru-core` (source of truth for shared types); `guru-graph` imports them.

### Shared types (`guru-core/src/guru_core/graph_types.py`)

```python
class KbNode(BaseModel):
    name: str
    project_root: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None   # liveness, hydrated at query time
    tags: list[str] = []                   # free-form taxonomy; NOT Neo4j labels
    metadata: dict[str, Any] = {}          # stored as metadata_json in Neo4j

class KbUpsert(BaseModel):
    name: str
    project_root: str
    tags: list[str] = []
    metadata: dict[str, Any] = {}

class KbLink(BaseModel):
    from_kb: str
    to_kb: str
    kind: LinkKind                         # controlled vocabulary, see below
    created_at: datetime
    metadata: dict[str, Any] = {}

class LinkKind(str, Enum):
    DEPENDS_ON = "depends_on"
    FORK_OF = "fork_of"
    REFERENCES = "references"
    RELATED_TO = "related_to"
    MIRRORS = "mirrors"

class CypherQuery(BaseModel):
    cypher: str
    params: dict[str, Any] = {}
    read_only: bool = True

class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    elapsed_ms: float

class Health(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    graph_reachable: bool
    backend: str                           # "neo4j"
    backend_version: str                   # "5.24.0" etc.
    schema_version: int

class VersionInfo(BaseModel):
    protocol_version: str                  # "1.0.0" semver
    backend: str
    backend_version: str
    schema_version: int
```

### Controlled vocabulary for `LinkKind`

MVP ships with a closed enum. Each value is documented inline in `graph_types.py` via docstring entries. Extending the vocabulary is a minor-version protocol bump (additive). Renaming or removing a value is a major-version bump.

| Kind | Meaning |
|---|---|
| `depends_on` | Source KB relies on target KB at runtime or build time (library, service, module dependency). |
| `fork_of` | Source KB was forked / derived from target KB's code history. |
| `references` | Source KB references target KB textually or semantically, without a hard dependency (docs, design notes, changelog). |
| `related_to` | Generic lightweight association; use sparingly when no stronger kind applies. |
| `mirrors` | Source KB is a functional or code-level mirror of target (vendored copy, cross-language port). |

Unknown `kind` values in `POST /kbs/{name}/links` are rejected with `422 Unprocessable Entity` and a clear message listing supported kinds.

### Cypher escape hatch (`POST /query`)

- Body: `{cypher, params, read_only}`.
- `read_only: true` routes through `GraphBackend.execute_read`; Neo4j's driver enforces read-only at the session level (`session.execute_read`). We do **not** attempt to parse Cypher to "detect" reads.
- Response: `{columns, rows, elapsed_ms}`.
- AuthN: UDS permission bits (socket is `0600`). Same-UID-same-machine is our trust boundary.
- The escape hatch is documented as a power-tool; writes to `:Kb` / `:LINKS` / `:_Meta` from here can break the domain contract. It is deliberately not sandboxed.

### `GraphClient` in `guru-core`

```python
class GraphClient:
    """HTTP-over-UDS client. Lives in guru-core so guru-server, guru-cli,
    and guru-mcp can share it. Never imports the Neo4j driver."""

    async def upsert_kb(self, req: KbUpsert) -> KbNode: ...
    async def get_kb(self, name: str) -> KbNode | None: ...
    async def list_kbs(self, *, prefix: str | None = None,
                       tag: str | None = None) -> list[KbNode]: ...
    async def delete_kb(self, name: str) -> bool: ...
    async def link_kbs(self, from_kb: str, to_kb: str,
                       kind: LinkKind, **meta) -> KbLink: ...
    async def unlink_kbs(self, from_kb: str, to_kb: str,
                         kind: LinkKind) -> bool: ...
    async def list_links(self, name: str,
                         direction: Literal["in","out","both"] = "both",
                         ) -> list[KbLink]: ...
    async def query(self, cypher: str, params: dict | None = None,
                    read_only: bool = True) -> QueryResult: ...
    async def health(self) -> Health: ...
    async def version(self) -> VersionInfo: ...
```

Every method raises `GraphUnavailable` on any of: ECONNREFUSED, ENOENT, 503, `426 Upgrade Required` (protocol mismatch), timeout, stale socket.

### `graph_or_skip` helper in guru-server

```python
async def graph_or_skip(coro, *, feature: str) -> Any | None:
    try:
        return await coro
    except GraphUnavailable as e:
        _log_once_per_process(feature, e)
        return None
```

Every graph call site in `guru-server` goes through this helper. This enforces the "optional feature, degrade silently" requirement architecturally rather than by convention.

---

## Schema, versioning & compatibility

Three distinct version axes, each with its own contract:

| Axis | Scope | Example | Location |
|---|---|---|---|
| **Protocol version** | Wire between `GraphClient` and `guru-graph` daemon | `1.0.0` (semver) | `GET /version`; `X-Guru-Graph-Protocol` request header |
| **Schema version** | Graph DB schema (labels, constraints, relationships) | `1` (integer) | property on `(:_Meta {kind: 'schema'})` node |
| **Backend version** | Neo4j engine itself | `5.24.0` | reported by Neo4j; not negotiated |

### Protocol compatibility policy (semver, strict)

- Client sends `X-Guru-Graph-Protocol: <semver>` on every request.
- Server responds `426 Upgrade Required` with body `{"supported": ["1.x"]}` when **MAJOR** differs.
- Server accepts any **MINOR** ≤ its own — older clients keep working when the server is upgraded (forward-compat).
- Client treats unknown response fields as pass-through (forward-compat for new server minors).
- Commitment: one MAJOR window — both sides require `client.MAJOR == server.MAJOR`; within a MAJOR, each side tolerates the other's MINOR being newer or older (unknown fields ignored; missing features degraded). Breaking changes bump MAJOR.

### Initial schema (`schema_version = 1`)

```cypher
// Node labels
(:Kb    { name, project_root, created_at, updated_at, tags [], metadata_json })
(:_Meta { kind, schema_version, protocol_version, created_at })

// Constraints
CREATE CONSTRAINT kb_name_unique FOR (k:Kb) REQUIRE k.name IS UNIQUE;
// Note: Neo4j Community has no NODE KEY / row-count constraints; the :_Meta node
// is kept singleton by disciplined MERGE: MERGE (m:_Meta {kind: 'schema'}) SET ...
// No server-side singleton constraint is created (it would enforce kind-uniqueness,
// not node-count, and could be satisfied by multiple rows with different kinds).

// Indexes
CREATE INDEX kb_updated_at FOR (k:Kb) ON (k.updated_at);

// Relationships
(:Kb)-[:LINKS { kind, created_at, metadata_json }]->(:Kb)
```

Design notes:

- `metadata` is serialised to a JSON string (`metadata_json`) on the Neo4j node/rel. Properties-as-JSON is not Cypher-queryable by key; this is the deliberate MVP tradeoff. Promoting specific keys to first-class properties is a schema migration (→ v2).
- Links use a single relationship type (`:LINKS`) with `kind` as a property, not dynamic relationship types. Keeps the label/type catalogue bounded. Filter with `MATCH (a)-[r:LINKS {kind:'depends_on'}]->(b)`.
- `(:Kb)` has a built-in Neo4j label plus a user-facing `tags[]` property. We renamed from "labels[]" to avoid confusing collision with Neo4j's own label concept.

### Migrations (forward-only)

```
packages/guru-graph/guru_graph/migrations/
  __init__.py
  m0001_initial.py     # creates :_Meta, constraints, indexes
  # future: m0002_*.py, m0003_*.py, ...
```

- Each migration: Python function taking `GraphBackend`; runs Cypher in a transaction; idempotent by checking `schema_version` before running.
- On daemon startup (after Neo4j is ready), `backend.ensure_schema(target=LATEST)` runs pending migrations in order.
- If `current > target` (older daemon against a newer store) → daemon exits with `"Graph store is schema v{N}; this daemon only supports up to v{M}. Upgrade the daemon or wipe ~/Library/Application Support/guru/graph/."`. No automatic downgrade. No silent data loss.
- No down-migrations in MVP.

### Data-model change policy

| Change | Category | Protocol bump | Schema bump |
|---|---|---|---|
| Add new property | Additive | MINOR (new field in response) | bump |
| Add new relationship type | Additive | MINOR (new domain endpoint) | bump |
| Add new `LinkKind` value | Additive | MINOR | no bump (same property) |
| Remove/rename property | Breaking | MAJOR | bump |
| Remove/rename `LinkKind` value | Breaking | MAJOR | no bump |
| Change cardinality / constraint | Breaking | MAJOR | bump |

### Reserved for future

- `POST /admin/dump` / `POST /admin/load` endpoints, `guru graph export` / `guru graph import` CLI commands, JSONL format — documented here as shapes to reserve so adding them is a MINOR bump. Not built in v1.
- Per-project namespacing inside the graph — future work if federation grows beyond the single-machine assumption.

---

## Testing strategy

Follows the project's existing three-tier convention + BDD e2e. Adds `@real_neo4j` as the heavy-runtime tag (mirrors `@real_ollama`).

### Tier 1 — Unit (`packages/guru-graph/tests/unit/`)

A `FakeBackend` implementing `GraphBackend` with in-memory `dict[str, Node]` + adjacency map. Deliberately does **not** parse Cypher; domain tests reach only the declarative methods. Lives at `packages/guru-graph/guru_graph/testing/fake_backend.py` and is exported so cross-package tests can use it.

- `test_kb_service.py` — upsert/get/list/delete/link/unlink/list_links; upsert idempotency.
- `test_versioning.py` — protocol parser, negotiation matrix, migration guard (refuse when `current > target`).
- `test_models.py` — Pydantic validation; metadata JSON round-trip; datetime serialisation.
- `test_link_vocabulary.py` — rejecting unknown `LinkKind`; enum round-trip.
- `test_graph_unavailable.py` — `GraphClient` raises `GraphUnavailable` on ECONNREFUSED, 503, 426, stale socket, timeout.
- `test_lifecycle.py` — daemon lazy-start race (concurrent clients, only one daemon spawned) using mocked `flock` + socket bind.

### Tier 2 — Integration (`packages/guru-graph/tests/integration/`)

- `test_routes_fake_backend.py` — FastAPI `TestClient` with `FakeBackend` injected. Covers HTTP contract: status codes, header negotiation, request/response shapes, error bodies. No Neo4j, fast.
- `test_neo4j_backend.py` — `@pytest.mark.real_neo4j`. Real Neo4j. Exercises `execute`, `execute_read`, transactions, constraint violations.
- `test_migrations.py` — `@real_neo4j`. Applies `m0001` to an empty store; verifies meta node, constraints, indexes; applies twice (idempotence); refuses on `current > target`.
- `test_escape_hatch.py` — `@real_neo4j`. `/query` read-only round-trips rows; writable queries succeed; malformed Cypher returns a structured error.

### Tier 3 — Cross-package integration (`tests/test_graph_integration.py`)

- graph disabled (config) → `guru-server` runs normally, no daemon spawned, `/status.graph_reachable=false`.
- graph enabled → lazy-start end-to-end.
- daemon killed mid-session → next call surfaces `GraphUnavailable`; `guru-server` continues; `/status` reflects.
- Neo4j preflight fails → daemon exits with actionable error; `guru-server` logs and continues degraded.

### Tier 4 — BDD e2e (`tests/e2e/features/graph_plugin.feature`)

Part of the spec per the constitution. All scenarios tagged `@real_neo4j` except those that test the disabled / unreachable paths.

```gherkin
Feature: Optional graph plugin

  @disabled
  Scenario: Graph disabled by config → guru-server works and reports degraded
    Given graph is disabled in global config
    When I start guru-server and check status
    Then status reports graph_reachable = false
    And index, search, and status endpoints all succeed

  @real_neo4j
  Scenario: Graph enabled → KB auto-registers on first server start
    Given graph is enabled in global config
    When I start guru-server for project "demo"
    Then a guru-graph daemon is running
    And a (:Kb {name: "demo"}) node exists in the graph

  @real_neo4j
  Scenario: Two projects share one graph daemon
    Given graph is enabled and a server is running for project "alpha"
    When I start a server for project "beta"
    Then both KB nodes exist
    And only one guru-graph daemon PID is alive

  @real_neo4j
  Scenario: Daemon crash triggers lazy restart on next use
    Given graph is enabled and a daemon is running
    When I SIGKILL the daemon and issue an upsert
    Then a new daemon is spawned within 5 seconds
    And the upsert succeeds

  @real_neo4j @slow
  Scenario: Neo4j crash → one retry then unhealthy degrade
    Given graph is enabled and a daemon is running
    When neo4j is killed twice in quick succession
    Then guru-graph reports 503 graph_unavailable
    And guru-server continues with graph_reachable = false

  Scenario: Neo4j preflight failure degrades silently
    Given graph is enabled but neo4j is not on PATH
    When I start guru-server
    Then guru-server starts successfully
    And status reports graph_reachable = false
    And the preflight error appears in the daemon log

  Scenario: Protocol MAJOR mismatch refused cleanly
    Given a daemon speaking protocol 2.x
    And a client speaking protocol 1.x
    When the client issues any request
    Then the server returns 426 Upgrade Required
    And GraphClient raises GraphUnavailable

  @real_neo4j
  Scenario: KB-to-KB link with known vocabulary succeeds
    Given KBs "alpha" and "beta" exist
    When I link alpha -> beta as depends_on
    Then list_links(alpha, out) contains (alpha, beta, depends_on)

  Scenario: Unknown link kind rejected
    Given KBs "alpha" and "beta" exist
    When I attempt to link alpha -> beta as "sorta_related"
    Then the response is 422
    And the error lists supported link kinds
```

### CI wiring

- `make test` (default) runs unit + integration **without** `@real_neo4j` → fast, no Neo4j dependency.
- New target `make test-graph` runs all graph tests including `@real_neo4j`. Requires local Neo4j or a testcontainer.
- `.github/workflows/ci.yml` grows a `graph-plugin` job: Neo4j 5.x service container, gated behind the `require-e2e-tests` label (same pattern as `@real_ollama`).
- Local dev convenience: `scripts/start-test-neo4j.sh` launches an ephemeral Neo4j via testcontainers-python.

---

## Packages & files (implementation sketch)

```
packages/guru-graph/
  pyproject.toml                           # depends on guru-core, neo4j, fastapi, uvicorn
  src/guru_graph/
    __init__.py
    main.py                                # daemon entrypoint (double-fork, serve FastAPI over UDS)
    app.py                                 # FastAPI app factory
    config.py                              # paths, port allocation, platform dirs
    lifecycle.py                           # lazy-start, flock, leader election, pidfile
    preflight.py                           # java/neo4j version checks
    neo4j_process.py                       # manages the Neo4j subprocess
    routes/
      __init__.py
      kbs.py                               # KB CRUD routes
      links.py                             # link routes
      query.py                             # Cypher escape hatch
      admin.py                             # /health, /version
    services/
      __init__.py
      kb_service.py                        # domain ops
      schema_service.py                    # migration orchestration
    backend/
      __init__.py
      base.py                              # GraphBackend Protocol + registry
      neo4j_backend.py                     # concrete implementation
    migrations/
      __init__.py
      m0001_initial.py
    testing/
      __init__.py
      fake_backend.py                      # in-memory test backend
    versioning.py                          # protocol version constants + negotiation
  tests/
    unit/
    integration/

packages/guru-core/
  src/guru_core/
    graph_types.py                         # NEW — shared Pydantic models + LinkKind enum
    graph_client.py                        # NEW — GraphClient over HTTP-UDS
    graph_errors.py                        # NEW — GraphUnavailable, etc.

packages/guru-server/
  src/guru_server/
    graph_integration.py                   # NEW — guru-server <-> graph glue (upsert self KB on boot, graph_or_skip helper)
    app.py                                 # touches: call graph_integration on startup, expose graph_reachable on /status

packages/guru-cli/
  src/guru_cli/
    commands/
      graph.py                             # NEW — `guru graph start|stop|status`

tests/e2e/features/
  graph_plugin.feature                     # NEW
  steps/graph_steps.py                     # NEW

docs/
  ARCHITECTURE.md                          # amended (see §constitution amendments)
```

No MCP touch in MVP — agents don't talk to the graph yet.

---

## Open questions / future work

- **Idle timeout.** Daemon currently stays up indefinitely. Consider an idle-timeout configuration once we have telemetry on how often the daemon sits unused.
- **MCP surface.** Add graph query tools to `guru-mcp` once artifact-level modelling arrives and the agent-facing query shape is meaningful.
- **Per-project namespacing.** Today all KBs share a single Neo4j database. If the machine-wide model strains, partition via a `namespace` property + index, or promote to Enterprise multi-database.
- **Backup / export / import.** Shapes reserved; implementation in v1.1.
- **Second backend.** The abstraction is designed for swap. Good candidates to prototype: Memgraph (BSL, C++, faster), LadybugDB (Apache 2, pip-only, embedded — no daemon).

---

## Success criteria

- `make test` runs green without Neo4j installed on the machine.
- `make test-graph` runs green with a real Neo4j.
- `guru-server` boots cleanly in all four states: graph disabled / graph enabled+reachable / graph enabled+unreachable / graph enabled+preflight-failed.
- `graph.enabled == true` on a fresh machine → first `guru index` creates a `(:Kb)` node visible via `POST /query` round-trip.
- Two projects on the same machine, both with graph enabled → single daemon, two KB nodes, linkable via the domain API.
- All BDD scenarios pass.
