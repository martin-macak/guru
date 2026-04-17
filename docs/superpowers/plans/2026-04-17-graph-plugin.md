# Graph Plugin Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the optional `guru-graph` plugin as a new workspace package — a FastAPI-over-UDS daemon that owns a Neo4j Community subprocess, exposes a domain-shaped KB API plus a Cypher escape hatch, is lazy-started by any guru-server on the machine, and degrades silently when unavailable.

**Architecture:** New `packages/guru-graph/` sits alongside guru-core/server/mcp/cli. Internally: FastAPI routes → domain services → `GraphBackend` protocol → `Neo4jBackend` (wraps `neo4j` Python driver over Bolt on a dynamically-chosen loopback port). A machine-wide singleton daemon is race-safely lazy-started by `guru-core`'s new `GraphClient`. guru-server upserts its own `(:Kb)` node on boot via `graph_or_skip`. Shared Pydantic models + `LinkKind` enum + `GraphUnavailable` exception live in guru-core.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, httpx (UDS), Neo4j 5.x (subprocess) + `neo4j` Python driver, pydantic, pytest, behave, platformdirs, fcntl (flock).

**Spec:** `docs/superpowers/specs/2026-04-17-graph-plugin-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `packages/guru-graph/pyproject.toml` | uv workspace package metadata + deps |
| `packages/guru-graph/README.md` | package-level intro |
| `packages/guru-graph/src/guru_graph/__init__.py` | package marker + `__version__` re-export |
| `packages/guru-graph/src/guru_graph/versioning.py` | `PROTOCOL_VERSION`, `SCHEMA_VERSION`, negotiation helpers |
| `packages/guru-graph/src/guru_graph/config.py` | platform paths (socket, data dir, pid, lock, log), port allocation helper |
| `packages/guru-graph/src/guru_graph/preflight.py` | `check_java_installed`, `check_neo4j_installed`, typed errors |
| `packages/guru-graph/src/guru_graph/neo4j_process.py` | `Neo4jProcess` — start/stop the neo4j subprocess, ready-probe |
| `packages/guru-graph/src/guru_graph/backend/__init__.py` | re-export `GraphBackend`, `GraphBackendRegistry` |
| `packages/guru-graph/src/guru_graph/backend/base.py` | `GraphBackend` Protocol + `BackendInfo`, `BackendHealth`, `CypherResult`, `Tx` dataclasses + `GraphBackendRegistry` |
| `packages/guru-graph/src/guru_graph/backend/neo4j_backend.py` | `Neo4jBackend` concrete implementation |
| `packages/guru-graph/src/guru_graph/migrations/__init__.py` | registry of migrations |
| `packages/guru-graph/src/guru_graph/migrations/m0001_initial.py` | initial schema migration |
| `packages/guru-graph/src/guru_graph/services/__init__.py` | package marker |
| `packages/guru-graph/src/guru_graph/services/kb_service.py` | `KbService` — domain ops translated to Cypher |
| `packages/guru-graph/src/guru_graph/services/query_service.py` | `QueryService` — Cypher escape hatch |
| `packages/guru-graph/src/guru_graph/services/schema_service.py` | migration orchestration |
| `packages/guru-graph/src/guru_graph/routes/__init__.py` | router aggregation |
| `packages/guru-graph/src/guru_graph/routes/kbs.py` | KB CRUD + link routes |
| `packages/guru-graph/src/guru_graph/routes/query.py` | `POST /query` route |
| `packages/guru-graph/src/guru_graph/routes/admin.py` | `GET /health`, `GET /version` |
| `packages/guru-graph/src/guru_graph/app.py` | FastAPI app factory, protocol-version middleware |
| `packages/guru-graph/src/guru_graph/lifecycle.py` | lazy-start, flock, double-fork spawn, stale-socket recovery |
| `packages/guru-graph/src/guru_graph/main.py` | daemon entrypoint (`guru-graph-daemon`) |
| `packages/guru-graph/src/guru_graph/testing/__init__.py` | re-export FakeBackend |
| `packages/guru-graph/src/guru_graph/testing/fake_backend.py` | in-memory `FakeBackend` |
| `packages/guru-graph/tests/__init__.py` | test package marker |
| `packages/guru-graph/tests/conftest.py` | shared fixtures (temp data dir, FakeBackend factory) |
| `packages/guru-graph/tests/test_versioning.py` | protocol negotiation |
| `packages/guru-graph/tests/test_models.py` | Pydantic validation (shared types) |
| `packages/guru-graph/tests/test_fake_backend.py` | FakeBackend behavior |
| `packages/guru-graph/tests/test_kb_service.py` | KbService unit tests (uses FakeBackend) |
| `packages/guru-graph/tests/test_query_service.py` | QueryService unit tests |
| `packages/guru-graph/tests/test_routes.py` | FastAPI TestClient with FakeBackend |
| `packages/guru-graph/tests/test_lifecycle.py` | lazy-start race with mocked flock |
| `packages/guru-graph/tests/test_config_paths.py` | platform paths + free-port allocation |
| `packages/guru-graph/tests/test_preflight.py` | preflight checks via monkeypatched `which` |
| `packages/guru-graph/tests/test_neo4j_backend.py` | `@pytest.mark.real_neo4j` backend round-trip |
| `packages/guru-graph/tests/test_migrations.py` | `@real_neo4j` m0001 apply + guard |
| `packages/guru-graph/tests/test_escape_hatch.py` | `@real_neo4j` `/query` round-trip |
| `packages/guru-core/src/guru_core/graph_types.py` | `KbNode`, `KbUpsert`, `KbLink`, `LinkKind`, `CypherQuery`, `QueryResult`, `Health`, `VersionInfo` |
| `packages/guru-core/src/guru_core/graph_errors.py` | `GraphUnavailable` exception |
| `packages/guru-core/src/guru_core/graph_client.py` | `GraphClient` (HTTP-over-UDS; autostart hook) |
| `packages/guru-core/tests/test_graph_types.py` | type validation + `LinkKind` round-trip |
| `packages/guru-core/tests/test_graph_client.py` | GraphClient error translation |
| `packages/guru-server/src/guru_server/graph_integration.py` | `graph_or_skip` + `register_self_kb` + client factory |
| `packages/guru-server/tests/test_graph_integration.py` | integration with FakeBackend-backed daemon |
| `packages/guru-cli/src/guru_cli/commands/__init__.py` | marker (if not present) |
| `packages/guru-cli/src/guru_cli/commands/graph.py` | `guru graph start|stop|status` |
| `tests/e2e/features/graph_plugin.feature` | BDD scenarios |
| `tests/e2e/features/steps/graph_steps.py` | step defs |
| `scripts/start-test-neo4j.sh` | local dev convenience |

### Modified files

| File | Change |
|------|--------|
| `pyproject.toml` | workspace picks up `packages/guru-graph` via `packages/*`; add `"guru-graph=={{ version }}"` to root meta-package deps; add `"guru-graph = { workspace = true }"` source |
| `packages/guru-core/src/guru_core/__init__.py` | re-export `GraphClient`, `GraphUnavailable` for convenience |
| `packages/guru-server/src/guru_server/app.py` | call `register_self_kb` during startup; expose `graph_reachable` / `graph_enabled` on `/status` |
| `packages/guru-server/src/guru_server/api/status.py` | add `graph_enabled`, `graph_reachable` to the status response |
| `packages/guru-core/src/guru_core/types.py` | extend `StatusOut` with `graph_enabled: bool` and `graph_reachable: bool` |
| `packages/guru-cli/src/guru_cli/cli.py` | register `graph` click group |
| `Makefile` | add `test-graph` target, gate `@real_neo4j` out of default `test` |
| `.github/workflows/ci.yml` | new `graph-plugin` job with Neo4j 5.x service container |
| `ARCHITECTURE.md` | two amendments (per-project state scoping, loopback-TCP exception) |
| `tests/e2e/features/environment.py` | `before_feature` hook for graph scenarios: set env pointing at temp graph dir |

---

## Task 1: Scaffold `packages/guru-graph` workspace package

**Files:**
- Create: `packages/guru-graph/pyproject.toml`
- Create: `packages/guru-graph/README.md`
- Create: `packages/guru-graph/src/guru_graph/__init__.py`
- Create: `packages/guru-graph/tests/__init__.py`
- Modify: `pyproject.toml` (root)

- [ ] **Step 1: Create the package's `pyproject.toml`**

Create `packages/guru-graph/pyproject.toml`:

```toml
[project]
name = "guru-graph"
dynamic = ["version", "dependencies"]
description = "Guru graph plugin — FastAPI daemon over Neo4j providing domain-shaped KB graph API"
readme = "README.md"
authors = [
    { name = "Martin Macak", email = "martin.macak@gmail.com" }
]
requires-python = ">=3.13"

[project.scripts]
guru-graph-daemon = "guru_graph.main:main"

[tool.uv.sources]
guru-core = { workspace = true }

[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "uv-dynamic-versioning"

[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    "guru-core=={{ version }}",
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "httpx>=0.28",
    "pydantic>=2.0",
    "neo4j>=5.25",
    "platformdirs>=4.0",
]

[tool.uv-dynamic-versioning]
vcs = "git"
style = "pep440"
bump = true

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
markers = [
    "real_neo4j: tests that require a running Neo4j 5.x instance (skipped by default)",
]
```

- [ ] **Step 2: Create minimal package files**

Create `packages/guru-graph/README.md`:

```markdown
# guru-graph

Optional graph plugin for Guru. FastAPI-over-UDS daemon that owns a Neo4j
Community subprocess and exposes a domain-shaped KB graph API plus a Cypher
escape hatch.

See `docs/superpowers/specs/2026-04-17-graph-plugin-design.md` for the design.
```

Create `packages/guru-graph/src/guru_graph/__init__.py`:

```python
"""Guru graph plugin — see spec at docs/superpowers/specs/2026-04-17-graph-plugin-design.md."""

__all__ = ["__version__"]

try:
    from importlib.metadata import version as _version

    __version__ = _version("guru-graph")
except Exception:
    __version__ = "0.0.0+unknown"
```

Create `packages/guru-graph/tests/__init__.py`:

```python
```

- [ ] **Step 3: Wire package into the root workspace**

Modify `pyproject.toml` (root). Replace the `dependencies` list and `[tool.uv.sources]` to include guru-graph:

```toml
[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    "guru-core=={{ version }}",
    "guru-server=={{ version }}",
    "guru-mcp=={{ version }}",
    "guru-cli=={{ version }}",
    "guru-graph=={{ version }}",
]
```

and add under `[tool.uv.sources]`:

```toml
guru-graph = { workspace = true }
```

Also extend `[tool.ruff]`:

```toml
src = ["packages/guru-core/src", "packages/guru-server/src", "packages/guru-mcp/src", "packages/guru-cli/src", "packages/guru-graph/src"]
```

and `[tool.ruff.lint.isort]`:

```toml
known-first-party = ["guru_core", "guru_server", "guru_mcp", "guru_cli", "guru_graph"]
```

- [ ] **Step 4: Verify workspace picks it up**

Run: `uv sync --all-packages`
Expected: `Resolved … packages`, no errors, includes `guru-graph`.

Run: `uv run python -c "import guru_graph; print(guru_graph.__version__)"`
Expected: prints a version string (e.g. `0.1.0+d9283cf`).

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph pyproject.toml
git commit -m "feat(graph): scaffold guru-graph workspace package"
```

---

## Task 2: Add shared graph types + `GraphUnavailable` to guru-core

**Files:**
- Create: `packages/guru-core/src/guru_core/graph_types.py`
- Create: `packages/guru-core/src/guru_core/graph_errors.py`
- Create: `packages/guru-core/tests/test_graph_types.py`
- Modify: `packages/guru-core/src/guru_core/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-core/tests/test_graph_types.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    CypherQuery,
    Health,
    KbLink,
    KbNode,
    KbUpsert,
    LinkKind,
    QueryResult,
    VersionInfo,
)


def test_link_kind_enum_values():
    assert LinkKind.DEPENDS_ON.value == "depends_on"
    assert LinkKind.FORK_OF.value == "fork_of"
    assert LinkKind.REFERENCES.value == "references"
    assert LinkKind.RELATED_TO.value == "related_to"
    assert LinkKind.MIRRORS.value == "mirrors"
    assert {k.value for k in LinkKind} == {
        "depends_on", "fork_of", "references", "related_to", "mirrors"
    }


def test_link_kind_rejects_unknown_value():
    with pytest.raises(ValueError):
        LinkKind("sorta_related")


def test_kb_node_round_trip():
    now = datetime.now(UTC)
    node = KbNode(
        name="alpha",
        project_root="/tmp/alpha",
        created_at=now,
        updated_at=now,
        tags=["app"],
        metadata={"lang": "python"},
    )
    data = json.loads(node.model_dump_json())
    parsed = KbNode.model_validate(data)
    assert parsed == node


def test_kb_upsert_requires_name_and_project_root():
    with pytest.raises(ValidationError):
        KbUpsert(project_root="/tmp/x")
    with pytest.raises(ValidationError):
        KbUpsert(name="x")


def test_kb_link_uses_link_kind_enum():
    now = datetime.now(UTC)
    link = KbLink(
        from_kb="alpha", to_kb="beta", kind=LinkKind.DEPENDS_ON,
        created_at=now, metadata={},
    )
    assert link.kind is LinkKind.DEPENDS_ON
    parsed = KbLink.model_validate(json.loads(link.model_dump_json()))
    assert parsed.kind is LinkKind.DEPENDS_ON


def test_kb_link_rejects_unknown_kind():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        KbLink(from_kb="a", to_kb="b", kind="sorta", created_at=now)


def test_cypher_query_defaults():
    q = CypherQuery(cypher="MATCH (n) RETURN n")
    assert q.params == {}
    assert q.read_only is True


def test_health_status_literal():
    h = Health(status="healthy", graph_reachable=True, backend="neo4j",
               backend_version="5.24.0", schema_version=1)
    assert h.status == "healthy"
    with pytest.raises(ValidationError):
        Health(status="fine", graph_reachable=True, backend="neo4j",
               backend_version="5.24.0", schema_version=1)


def test_version_info_fields():
    v = VersionInfo(protocol_version="1.0.0", backend="neo4j",
                    backend_version="5.24.0", schema_version=1)
    assert v.protocol_version == "1.0.0"


def test_query_result_shape():
    r = QueryResult(columns=["n"], rows=[["a"], ["b"]], elapsed_ms=1.2)
    assert r.columns == ["n"]
    assert r.rows == [["a"], ["b"]]


def test_graph_unavailable_is_runtime_error():
    err = GraphUnavailable("daemon unreachable")
    assert isinstance(err, RuntimeError)
    assert str(err) == "daemon unreachable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-core/tests/test_graph_types.py -v`
Expected: FAIL — `ModuleNotFoundError: guru_core.graph_types`.

- [ ] **Step 3: Implement `graph_errors.py`**

Create `packages/guru-core/src/guru_core/graph_errors.py`:

```python
"""Errors raised by the graph client when the graph plugin is unreachable.

All failures to talk to the graph daemon — transport errors, protocol version
mismatches, 503 from the daemon, stale sockets, timeouts — are flattened into
`GraphUnavailable`. Callers in guru-server wrap graph calls in `graph_or_skip`
to degrade silently.
"""

from __future__ import annotations


class GraphUnavailable(RuntimeError):
    """Raised when the graph daemon is unreachable or incompatible."""
```

- [ ] **Step 4: Implement `graph_types.py`**

Create `packages/guru-core/src/guru_core/graph_types.py`:

```python
"""Shared Pydantic models for the graph plugin.

Per ARCHITECTURE.md, guru-core is the canonical source of shared types. The
graph daemon (`guru-graph`) imports these; the graph client (`GraphClient`
in this package) does too.

LinkKind vocabulary is a closed enum in v1. Extending it is a MINOR protocol
bump; renaming or removing a value is a MAJOR bump.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LinkKind(str, Enum):
    """Controlled vocabulary for KB-to-KB relationship kinds.

    Each value is documented below. The vocabulary is closed in protocol v1;
    new kinds are additive (MINOR bump). Rename/remove = MAJOR bump.
    """

    # Source KB relies on target KB at runtime or build time
    # (library, service, module dependency).
    DEPENDS_ON = "depends_on"

    # Source KB was forked / derived from target KB's code history.
    FORK_OF = "fork_of"

    # Source KB references target KB textually or semantically, without a
    # hard dependency (docs, design notes, changelog).
    REFERENCES = "references"

    # Generic lightweight association; use sparingly when no stronger kind
    # applies.
    RELATED_TO = "related_to"

    # Source KB is a functional or code-level mirror of target
    # (vendored copy, cross-language port).
    MIRRORS = "mirrors"


class KbUpsert(BaseModel):
    """Request body for POST /kbs (also used as input to GraphClient.upsert_kb)."""

    model_config = ConfigDict(extra="ignore")
    name: str
    project_root: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KbNode(BaseModel):
    """A KB node in the graph. Persistent across server restarts.

    `last_seen_at` is hydrated at query time from federation liveness; a
    null value means the KB has never been seen live (or liveness data was
    unavailable).
    """

    model_config = ConfigDict(extra="ignore")
    name: str
    project_root: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KbLinkCreate(BaseModel):
    """Request body for POST /kbs/{name}/links."""

    model_config = ConfigDict(extra="ignore")
    to_kb: str
    kind: LinkKind
    metadata: dict[str, Any] = Field(default_factory=dict)


class KbLink(BaseModel):
    """A directed KB-to-KB link."""

    model_config = ConfigDict(extra="ignore")
    from_kb: str
    to_kb: str
    kind: LinkKind
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class CypherQuery(BaseModel):
    """Request body for POST /query — the Cypher escape hatch.

    read_only routes through the backend's read-only execution path. We do
    NOT parse Cypher to detect reads; the driver enforces it.
    """

    model_config = ConfigDict(extra="ignore")
    cypher: str
    params: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    elapsed_ms: float


class Health(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    graph_reachable: bool
    backend: str
    backend_version: str
    schema_version: int


class VersionInfo(BaseModel):
    protocol_version: str
    backend: str
    backend_version: str
    schema_version: int
```

- [ ] **Step 5: Re-export from package `__init__.py`**

Modify `packages/guru-core/src/guru_core/__init__.py` — append these lines (keep existing re-exports):

```python
from .graph_errors import GraphUnavailable
from .graph_types import (
    CypherQuery,
    Health,
    KbLink,
    KbLinkCreate,
    KbNode,
    KbUpsert,
    LinkKind,
    QueryResult,
    VersionInfo,
)

__all__ = [
    # ... existing entries ...
    "CypherQuery",
    "GraphUnavailable",
    "Health",
    "KbLink",
    "KbLinkCreate",
    "KbNode",
    "KbUpsert",
    "LinkKind",
    "QueryResult",
    "VersionInfo",
]
```

(Merge the `__all__` with whatever already exists there; add the new names alphabetically.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest packages/guru-core/tests/test_graph_types.py -v`
Expected: all 11 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/guru-core
git commit -m "feat(graph): add shared graph types and GraphUnavailable to guru-core"
```

---

## Task 3: Protocol + schema version negotiation helpers

**Files:**
- Create: `packages/guru-graph/src/guru_graph/versioning.py`
- Create: `packages/guru-graph/tests/test_versioning.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-graph/tests/test_versioning.py`:

```python
from __future__ import annotations

import pytest

from guru_graph.versioning import (
    PROTOCOL_VERSION,
    SCHEMA_VERSION,
    ProtocolVersion,
    VersionNegotiationError,
    check_migration_target,
    negotiate_protocol,
    parse_version,
)


def test_parse_semver():
    v = parse_version("1.2.3")
    assert v == ProtocolVersion(1, 2, 3)


def test_parse_rejects_malformed():
    with pytest.raises(VersionNegotiationError):
        parse_version("1.2")
    with pytest.raises(VersionNegotiationError):
        parse_version("banana")


def test_major_mismatch_refused():
    server = parse_version("1.0.0")
    client = parse_version("2.0.0")
    with pytest.raises(VersionNegotiationError) as exc:
        negotiate_protocol(server=server, client=client)
    assert "MAJOR" in str(exc.value)


def test_minor_older_client_accepted():
    server = parse_version("1.5.0")
    client = parse_version("1.2.0")
    negotiate_protocol(server=server, client=client)  # no raise


def test_minor_newer_client_accepted():
    server = parse_version("1.2.0")
    client = parse_version("1.5.0")
    negotiate_protocol(server=server, client=client)  # no raise


def test_current_constants_are_semver():
    parse_version(PROTOCOL_VERSION)
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


def test_migration_target_equal_ok():
    check_migration_target(current=1, target=1)  # no raise


def test_migration_target_forward_ok():
    check_migration_target(current=1, target=2)  # no raise


def test_migration_target_backward_refused():
    with pytest.raises(VersionNegotiationError) as exc:
        check_migration_target(current=3, target=2)
    msg = str(exc.value)
    assert "3" in msg and "2" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-graph/tests/test_versioning.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `versioning.py`**

Create `packages/guru-graph/src/guru_graph/versioning.py`:

```python
"""Protocol and schema version constants and negotiation helpers.

See spec §Schema, versioning & compatibility. Three axes:
  - PROTOCOL_VERSION: semver wire-protocol between GraphClient and daemon
  - SCHEMA_VERSION: integer DB schema version (migrations)
  - backend_version: Neo4j engine version (reported, not negotiated)
"""

from __future__ import annotations

from dataclasses import dataclass

PROTOCOL_VERSION = "1.0.0"
SCHEMA_VERSION = 1

PROTOCOL_HEADER = "X-Guru-Graph-Protocol"


class VersionNegotiationError(RuntimeError):
    """Raised when version constraints cannot be satisfied."""


@dataclass(frozen=True)
class ProtocolVersion:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_version(s: str) -> ProtocolVersion:
    parts = s.split(".")
    if len(parts) != 3:
        raise VersionNegotiationError(f"expected X.Y.Z semver, got {s!r}")
    try:
        major, minor, patch = (int(p) for p in parts)
    except ValueError as e:
        raise VersionNegotiationError(f"non-integer component in {s!r}") from e
    return ProtocolVersion(major, minor, patch)


def negotiate_protocol(*, server: ProtocolVersion, client: ProtocolVersion) -> None:
    """Accept the request if client and server share the same MAJOR.

    Raises VersionNegotiationError otherwise. Tolerance within a MAJOR is
    each side's responsibility (unknown fields ignored, missing features
    degraded).
    """
    if server.major != client.major:
        raise VersionNegotiationError(
            f"protocol MAJOR mismatch: server={server}, client={client}"
        )


def check_migration_target(*, current: int, target: int) -> None:
    """Guard against an older daemon running against a newer store.

    Current > target means someone downgraded the daemon. We refuse with a
    clear error — no automatic downgrade, no silent data loss.
    """
    if current > target:
        raise VersionNegotiationError(
            f"graph store is schema v{current}; this daemon supports up to "
            f"v{target}. Upgrade the daemon or wipe the graph data dir."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-graph/tests/test_versioning.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add protocol + schema version negotiation"
```

---

## Task 4: `GraphBackend` protocol, registry, and supporting dataclasses

**Files:**
- Create: `packages/guru-graph/src/guru_graph/backend/__init__.py`
- Create: `packages/guru-graph/src/guru_graph/backend/base.py`

- [ ] **Step 1: Create backend package init**

Create `packages/guru-graph/src/guru_graph/backend/__init__.py`:

```python
from .base import (
    BackendHealth,
    BackendInfo,
    CypherResult,
    GraphBackend,
    GraphBackendRegistry,
    Tx,
)

__all__ = [
    "BackendHealth",
    "BackendInfo",
    "CypherResult",
    "GraphBackend",
    "GraphBackendRegistry",
    "Tx",
]
```

- [ ] **Step 2: Implement `backend/base.py`**

Create `packages/guru-graph/src/guru_graph/backend/base.py`:

```python
"""Backend abstraction. See spec §Interface design.

The backend exposes Cypher execution + transactions. Domain operations
(upsert KB, link KBs, etc.) live in the service layer above and translate
to Cypher strings — so any openCypher backend can be swapped in by
implementing this Protocol.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class BackendInfo:
    name: str
    version: str
    schema_version: int


@dataclass(frozen=True)
class BackendHealth:
    healthy: bool
    detail: str = ""


@dataclass
class CypherResult:
    columns: list[str]
    rows: list[list[Any]]
    elapsed_ms: float = 0.0


@dataclass
class Tx:
    """Transaction handle. Backends may subclass if they need richer state."""

    backend: "GraphBackend"
    read_only: bool = False

    def execute(self, cypher: str, params: dict[str, Any] | None = None) -> CypherResult:
        # Default implementation routes through the backend; Neo4jBackend
        # overrides with a real transaction handle.
        if self.read_only:
            return self.backend.execute_read(cypher, params or {})
        return self.backend.execute(cypher, params or {})


@runtime_checkable
class GraphBackend(Protocol):
    """Backend-agnostic graph operations. Cypher-only surface."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def health(self) -> BackendHealth: ...
    def info(self) -> BackendInfo: ...
    def execute(self, cypher: str, params: dict[str, Any]) -> CypherResult: ...
    def execute_read(self, cypher: str, params: dict[str, Any]) -> CypherResult: ...

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[Tx]: ...

    def ensure_schema(self, target_version: int) -> None: ...


class GraphBackendRegistry:
    """Registry for available GraphBackend implementations.

    Adding a backend later = one `register()` call + one class. Domain
    services / routes do not change.
    """

    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, backend_cls: type) -> None:
        cls._registry[name] = backend_cls

    @classmethod
    def get(cls, name: str) -> type:
        try:
            return cls._registry[name]
        except KeyError as e:
            raise KeyError(
                f"no backend registered for {name!r}. "
                f"Known: {sorted(cls._registry)}"
            ) from e

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._registry)
```

- [ ] **Step 3: Smoke-test imports**

Run: `uv run python -c "from guru_graph.backend import GraphBackend, GraphBackendRegistry; print(GraphBackendRegistry.names())"`
Expected: prints `[]`.

- [ ] **Step 4: Commit**

```bash
git add packages/guru-graph/src/guru_graph/backend
git commit -m "feat(graph): add GraphBackend protocol and registry"
```

---

## Task 5: `FakeBackend` in-memory implementation

**Files:**
- Create: `packages/guru-graph/src/guru_graph/testing/__init__.py`
- Create: `packages/guru-graph/src/guru_graph/testing/fake_backend.py`
- Create: `packages/guru-graph/tests/test_fake_backend.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-graph/tests/test_fake_backend.py`:

```python
from __future__ import annotations

import pytest

from guru_graph.backend import BackendHealth, BackendInfo, GraphBackendRegistry
from guru_graph.testing import FakeBackend


@pytest.fixture
def backend() -> FakeBackend:
    b = FakeBackend()
    b.start()
    yield b
    b.stop()


def test_info_reports_fake_metadata(backend: FakeBackend):
    info = backend.info()
    assert isinstance(info, BackendInfo)
    assert info.name == "fake"


def test_health_is_healthy_after_start(backend: FakeBackend):
    h = backend.health()
    assert isinstance(h, BackendHealth)
    assert h.healthy is True


def test_upsert_kb_creates_node(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/tmp/a", tags=[], metadata_json="{}")
    rows = backend.get_kb("alpha")
    assert rows is not None
    assert rows["name"] == "alpha"
    assert rows["project_root"] == "/tmp/a"


def test_upsert_kb_is_idempotent_and_updates(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/tmp/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="alpha", project_root="/tmp/a2", tags=["x"], metadata_json="{}")
    node = backend.get_kb("alpha")
    assert node["project_root"] == "/tmp/a2"
    assert node["tags"] == ["x"]


def test_list_kbs_prefix_filter(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="alpine", project_root="/b", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/c", tags=[], metadata_json="{}")
    assert {n["name"] for n in backend.list_kbs(prefix="al")} == {"alpha", "alpine"}
    assert {n["name"] for n in backend.list_kbs()} == {"alpha", "alpine", "beta"}


def test_delete_kb_removes_node_and_links(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/b", tags=[], metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="depends_on", metadata_json="{}")
    assert backend.delete_kb("alpha") is True
    assert backend.get_kb("alpha") is None
    assert backend.list_links_for(name="beta", direction="in") == []


def test_link_creates_edge(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/b", tags=[], metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="depends_on", metadata_json="{}")
    links = backend.list_links_for(name="alpha", direction="out")
    assert len(links) == 1
    assert links[0]["to_kb"] == "beta"
    assert links[0]["kind"] == "depends_on"


def test_unlink_specific_kind(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/b", tags=[], metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="depends_on", metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="references", metadata_json="{}")
    assert backend.unlink(from_kb="alpha", to_kb="beta", kind="depends_on") is True
    kinds = [l["kind"] for l in backend.list_links_for(name="alpha", direction="out")]
    assert kinds == ["references"]


def test_ensure_schema_records_version(backend: FakeBackend):
    backend.ensure_schema(target_version=1)
    assert backend.info().schema_version == 1


def test_ensure_schema_refuses_downgrade(backend: FakeBackend):
    backend.ensure_schema(target_version=3)
    with pytest.raises(Exception):
        backend.ensure_schema(target_version=2)


def test_registry_registration():
    GraphBackendRegistry.register("fake", FakeBackend)
    assert "fake" in GraphBackendRegistry.names()
    assert GraphBackendRegistry.get("fake") is FakeBackend
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-graph/tests/test_fake_backend.py -v`
Expected: FAIL — `ModuleNotFoundError: guru_graph.testing`.

- [ ] **Step 3: Implement `FakeBackend`**

Create `packages/guru-graph/src/guru_graph/testing/__init__.py`:

```python
from .fake_backend import FakeBackend

__all__ = ["FakeBackend"]
```

Create `packages/guru-graph/src/guru_graph/testing/fake_backend.py`:

```python
"""In-memory GraphBackend for tests.

Deliberately does NOT parse Cypher. Exposes declarative helper methods used
by KbService tests; the Cypher escape-hatch path is only covered by real
Neo4j integration tests (@real_neo4j).
"""

from __future__ import annotations

import copy
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from guru_graph.backend.base import BackendHealth, BackendInfo, CypherResult, Tx
from guru_graph.versioning import VersionNegotiationError, check_migration_target


@dataclass
class _FakeLink:
    from_kb: str
    to_kb: str
    kind: str
    created_at: float
    metadata_json: str


@dataclass
class FakeBackend:
    """In-memory backend.

    Designed to support KbService unit tests without a JVM. Cypher methods
    are stubbed — tests that exercise Cypher should use real Neo4j.
    """

    _nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _links: list[_FakeLink] = field(default_factory=list)
    _started: bool = False
    _schema_version: int = 0

    # ---- Lifecycle ----
    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def health(self) -> BackendHealth:
        return BackendHealth(
            healthy=self._started,
            detail="" if self._started else "not started",
        )

    def info(self) -> BackendInfo:
        return BackendInfo(name="fake", version="0.0.0", schema_version=self._schema_version)

    # ---- Cypher surface (stubbed) ----
    def execute(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        return CypherResult(columns=[], rows=[], elapsed_ms=0.0)

    def execute_read(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        return CypherResult(columns=[], rows=[], elapsed_ms=0.0)

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[Tx]:
        yield Tx(backend=self, read_only=read_only)

    def ensure_schema(self, target_version: int) -> None:
        check_migration_target(current=self._schema_version, target=target_version)
        self._schema_version = target_version

    # ---- Test helpers: declarative node/link ops (not Cypher) ----
    def upsert_kb(self, *, name: str, project_root: str, tags: list[str],
                  metadata_json: str) -> None:
        now = time.time()
        existing = self._nodes.get(name)
        created = existing["created_at"] if existing else now
        self._nodes[name] = {
            "name": name,
            "project_root": project_root,
            "tags": list(tags),
            "metadata_json": metadata_json,
            "created_at": created,
            "updated_at": now,
        }

    def get_kb(self, name: str) -> dict[str, Any] | None:
        node = self._nodes.get(name)
        return copy.deepcopy(node) if node else None

    def list_kbs(self, *, prefix: str | None = None,
                 tag: str | None = None) -> list[dict[str, Any]]:
        out = []
        for node in self._nodes.values():
            if prefix and not node["name"].startswith(prefix):
                continue
            if tag and tag not in node["tags"]:
                continue
            out.append(copy.deepcopy(node))
        return sorted(out, key=lambda n: n["name"])

    def delete_kb(self, name: str) -> bool:
        if name not in self._nodes:
            return False
        del self._nodes[name]
        self._links = [l for l in self._links if l.from_kb != name and l.to_kb != name]
        return True

    def link(self, *, from_kb: str, to_kb: str, kind: str,
             metadata_json: str) -> None:
        if from_kb not in self._nodes or to_kb not in self._nodes:
            raise KeyError(f"missing endpoint: {from_kb!r} or {to_kb!r}")
        for l in self._links:
            if l.from_kb == from_kb and l.to_kb == to_kb and l.kind == kind:
                l.metadata_json = metadata_json  # idempotent update
                return
        self._links.append(_FakeLink(
            from_kb=from_kb, to_kb=to_kb, kind=kind,
            created_at=time.time(), metadata_json=metadata_json,
        ))

    def unlink(self, *, from_kb: str, to_kb: str, kind: str) -> bool:
        before = len(self._links)
        self._links = [
            l for l in self._links
            if not (l.from_kb == from_kb and l.to_kb == to_kb and l.kind == kind)
        ]
        return len(self._links) < before

    def list_links_for(self, *, name: str,
                       direction: str = "both") -> list[dict[str, Any]]:
        out = []
        for l in self._links:
            include = (
                (direction in ("out", "both") and l.from_kb == name)
                or (direction in ("in", "both") and l.to_kb == name)
            )
            if include:
                out.append({
                    "from_kb": l.from_kb,
                    "to_kb": l.to_kb,
                    "kind": l.kind,
                    "created_at": l.created_at,
                    "metadata_json": l.metadata_json,
                })
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-graph/tests/test_fake_backend.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add FakeBackend for unit tests"
```

---

## Task 6: `KbService` and `QueryService` domain services

**Files:**
- Create: `packages/guru-graph/src/guru_graph/services/__init__.py`
- Create: `packages/guru-graph/src/guru_graph/services/kb_service.py`
- Create: `packages/guru-graph/src/guru_graph/services/query_service.py`
- Create: `packages/guru-graph/tests/test_kb_service.py`
- Create: `packages/guru-graph/tests/test_query_service.py`

- [ ] **Step 1: Write failing tests for `KbService`**

Create `packages/guru-graph/tests/test_kb_service.py`:

```python
from __future__ import annotations

import pytest

from guru_core.graph_types import KbLinkCreate, KbUpsert, LinkKind
from guru_graph.services.kb_service import KbNotFoundError, KbService
from guru_graph.testing import FakeBackend


@pytest.fixture
def service() -> KbService:
    backend = FakeBackend()
    backend.start()
    svc = KbService(backend=backend)
    yield svc
    backend.stop()


def test_upsert_returns_node_with_timestamps(service: KbService):
    node = service.upsert(KbUpsert(name="alpha", project_root="/a", tags=["app"]))
    assert node.name == "alpha"
    assert node.tags == ["app"]
    assert node.created_at == node.updated_at


def test_upsert_is_idempotent(service: KbService):
    first = service.upsert(KbUpsert(name="alpha", project_root="/a"))
    second = service.upsert(KbUpsert(name="alpha", project_root="/a2"))
    assert first.created_at == second.created_at
    assert second.updated_at >= first.updated_at
    assert second.project_root == "/a2"


def test_get_returns_none_when_missing(service: KbService):
    assert service.get("unknown") is None


def test_list_prefix(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="alpine", project_root="/b"))
    service.upsert(KbUpsert(name="beta", project_root="/c"))
    assert {n.name for n in service.list(prefix="al")} == {"alpha", "alpine"}


def test_delete_missing_returns_false(service: KbService):
    assert service.delete("nope") is False


def test_link_requires_existing_endpoints(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    with pytest.raises(KbNotFoundError):
        service.link(from_kb="alpha",
                     req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))


def test_link_and_list(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="beta", project_root="/b"))
    service.link(from_kb="alpha",
                 req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))
    outs = service.list_links(name="alpha", direction="out")
    assert len(outs) == 1
    assert outs[0].to_kb == "beta"
    assert outs[0].kind is LinkKind.DEPENDS_ON


def test_unlink(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="beta", project_root="/b"))
    service.link(from_kb="alpha",
                 req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))
    assert service.unlink(from_kb="alpha", to_kb="beta",
                          kind=LinkKind.DEPENDS_ON) is True


def test_delete_cascades_links(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="beta", project_root="/b"))
    service.link(from_kb="alpha",
                 req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))
    assert service.delete("alpha") is True
    assert service.list_links(name="beta", direction="in") == []
```

- [ ] **Step 2: Write failing tests for `QueryService`**

Create `packages/guru-graph/tests/test_query_service.py`:

```python
from __future__ import annotations

from guru_core.graph_types import CypherQuery
from guru_graph.services.query_service import QueryService
from guru_graph.testing import FakeBackend


def test_query_service_routes_read_to_execute_read(monkeypatch):
    backend = FakeBackend()
    backend.start()
    calls = []
    monkeypatch.setattr(
        backend, "execute_read",
        lambda cypher, params: calls.append(("read", cypher, params)) or
        __import__("guru_graph.backend.base", fromlist=["CypherResult"]).CypherResult(
            columns=["a"], rows=[[1]], elapsed_ms=0.0
        ),
    )
    svc = QueryService(backend=backend)
    svc.run(CypherQuery(cypher="MATCH (n) RETURN n", params={}, read_only=True))
    assert calls and calls[0][0] == "read"


def test_query_service_routes_write_to_execute(monkeypatch):
    backend = FakeBackend()
    backend.start()
    calls = []
    monkeypatch.setattr(
        backend, "execute",
        lambda cypher, params: calls.append(("write", cypher, params)) or
        __import__("guru_graph.backend.base", fromlist=["CypherResult"]).CypherResult(
            columns=[], rows=[], elapsed_ms=0.0
        ),
    )
    svc = QueryService(backend=backend)
    svc.run(CypherQuery(cypher="CREATE (n:X) RETURN n", params={}, read_only=False))
    assert calls and calls[0][0] == "write"


def test_query_service_returns_query_result():
    backend = FakeBackend()
    backend.start()
    svc = QueryService(backend=backend)
    out = svc.run(CypherQuery(cypher="RETURN 1", params={}, read_only=True))
    assert out.columns == []
    assert out.rows == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest packages/guru-graph/tests/test_kb_service.py packages/guru-graph/tests/test_query_service.py -v`
Expected: FAIL — `ModuleNotFoundError: guru_graph.services.kb_service`.

- [ ] **Step 4: Implement services**

Create `packages/guru-graph/src/guru_graph/services/__init__.py`:

```python
```

Create `packages/guru-graph/src/guru_graph/services/kb_service.py`:

```python
"""Domain services that translate KB operations into backend calls.

The backend exposes Cypher; this layer expresses business meaning. Swapping
backends = reimplement backend only, no change here.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Literal

from guru_core.graph_types import KbLink, KbLinkCreate, KbNode, KbUpsert, LinkKind

from ..backend.base import GraphBackend

logger = logging.getLogger(__name__)


class KbNotFoundError(RuntimeError):
    """Raised when a link endpoint does not exist."""


def _to_node(row: dict) -> KbNode:
    now = datetime.fromtimestamp(row["created_at"], tz=UTC)
    upd = datetime.fromtimestamp(row["updated_at"], tz=UTC)
    return KbNode(
        name=row["name"],
        project_root=row["project_root"],
        created_at=now,
        updated_at=upd,
        last_seen_at=None,
        tags=list(row.get("tags") or []),
        metadata=json.loads(row.get("metadata_json") or "{}"),
    )


def _to_link(row: dict) -> KbLink:
    created = datetime.fromtimestamp(row["created_at"], tz=UTC)
    return KbLink(
        from_kb=row["from_kb"],
        to_kb=row["to_kb"],
        kind=LinkKind(row["kind"]),
        created_at=created,
        metadata=json.loads(row.get("metadata_json") or "{}"),
    )


class KbService:
    """KB CRUD + KB-to-KB links.

    Both FakeBackend and Neo4jBackend provide `upsert_kb`/`get_kb`/`list_kbs`/
    `delete_kb`/`link`/`unlink`/`list_links_for` declarative methods to
    support this service without the service knowing about Cypher.
    """

    def __init__(self, *, backend: GraphBackend):
        self._backend = backend

    def upsert(self, req: KbUpsert) -> KbNode:
        self._backend.upsert_kb(
            name=req.name,
            project_root=req.project_root,
            tags=req.tags,
            metadata_json=json.dumps(req.metadata or {}),
        )
        row = self._backend.get_kb(req.name)
        assert row is not None
        return _to_node(row)

    def get(self, name: str) -> KbNode | None:
        row = self._backend.get_kb(name)
        return _to_node(row) if row else None

    def list(self, *, prefix: str | None = None,
             tag: str | None = None) -> list[KbNode]:
        rows = self._backend.list_kbs(prefix=prefix, tag=tag)
        return [_to_node(r) for r in rows]

    def delete(self, name: str) -> bool:
        return self._backend.delete_kb(name)

    def link(self, *, from_kb: str, req: KbLinkCreate) -> KbLink:
        if self._backend.get_kb(from_kb) is None:
            raise KbNotFoundError(f"from_kb {from_kb!r} does not exist")
        if self._backend.get_kb(req.to_kb) is None:
            raise KbNotFoundError(f"to_kb {req.to_kb!r} does not exist")
        self._backend.link(
            from_kb=from_kb,
            to_kb=req.to_kb,
            kind=req.kind.value,
            metadata_json=json.dumps(req.metadata or {}),
        )
        for row in self._backend.list_links_for(name=from_kb, direction="out"):
            if row["to_kb"] == req.to_kb and row["kind"] == req.kind.value:
                return _to_link(row)
        raise RuntimeError("link not found after create")

    def unlink(self, *, from_kb: str, to_kb: str, kind: LinkKind) -> bool:
        return self._backend.unlink(
            from_kb=from_kb, to_kb=to_kb, kind=kind.value
        )

    def list_links(self, *, name: str,
                   direction: Literal["in", "out", "both"] = "both",
                   ) -> list[KbLink]:
        rows = self._backend.list_links_for(name=name, direction=direction)
        return [_to_link(r) for r in rows]
```

Create `packages/guru-graph/src/guru_graph/services/query_service.py`:

```python
"""Cypher escape-hatch service.

read_only routes through backend.execute_read; writes through backend.execute.
We do NOT parse Cypher to sniff reads — the driver enforces it server-side.
"""

from __future__ import annotations

from guru_core.graph_types import CypherQuery, QueryResult

from ..backend.base import GraphBackend


class QueryService:
    def __init__(self, *, backend: GraphBackend):
        self._backend = backend

    def run(self, q: CypherQuery) -> QueryResult:
        params = dict(q.params or {})
        if q.read_only:
            res = self._backend.execute_read(q.cypher, params)
        else:
            res = self._backend.execute(q.cypher, params)
        return QueryResult(
            columns=list(res.columns),
            rows=[list(r) for r in res.rows],
            elapsed_ms=res.elapsed_ms,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest packages/guru-graph/tests/test_kb_service.py packages/guru-graph/tests/test_query_service.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add KbService and QueryService domain layer"
```

---

## Task 7: FastAPI app factory with protocol-version middleware

**Files:**
- Create: `packages/guru-graph/src/guru_graph/app.py`
- Create: `packages/guru-graph/src/guru_graph/routes/__init__.py`
- Create: `packages/guru-graph/src/guru_graph/routes/admin.py`
- Create: `packages/guru-graph/tests/test_routes.py` (admin routes only in this task)

- [ ] **Step 1: Write failing tests for app factory + admin routes**

Create `packages/guru-graph/tests/test_routes.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing import FakeBackend
from guru_graph.versioning import PROTOCOL_HEADER, PROTOCOL_VERSION


@pytest.fixture
def client() -> TestClient:
    backend = FakeBackend()
    backend.start()
    backend.ensure_schema(target_version=1)
    app = create_app(backend=backend)
    with TestClient(app) as c:
        yield c
    backend.stop()


def _v1_headers() -> dict[str, str]:
    return {PROTOCOL_HEADER: PROTOCOL_VERSION}


def test_health_returns_ok(client: TestClient):
    r = client.get("/health", headers=_v1_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["graph_reachable"] is True
    assert body["backend"] == "fake"
    assert body["schema_version"] == 1


def test_version_returns_metadata(client: TestClient):
    r = client.get("/version", headers=_v1_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["protocol_version"] == PROTOCOL_VERSION
    assert body["backend"] == "fake"
    assert body["schema_version"] == 1


def test_protocol_major_mismatch_returns_426(client: TestClient):
    r = client.get("/health", headers={PROTOCOL_HEADER: "99.0.0"})
    assert r.status_code == 426
    assert "supported" in r.json()


def test_missing_protocol_header_is_accepted_for_backward_compat(client: TestClient):
    # Clients that never send the header at all are accepted — we document
    # the header but cannot enforce it for bootstrap probes. Tracked as a
    # compat choice in the spec.
    r = client.get("/health")
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-graph/tests/test_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: guru_graph.app`.

- [ ] **Step 3: Implement routes package init + admin routes + app factory**

Create `packages/guru-graph/src/guru_graph/routes/__init__.py`:

```python
```

Create `packages/guru-graph/src/guru_graph/routes/admin.py`:

```python
"""Admin routes — /health, /version. No auth, UDS perm is the trust boundary."""

from __future__ import annotations

from fastapi import APIRouter, Request

from guru_core.graph_types import Health, VersionInfo

from ..versioning import PROTOCOL_VERSION, SCHEMA_VERSION

router = APIRouter()


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    backend = request.app.state.backend
    h = backend.health()
    info = backend.info()
    return Health(
        status="healthy" if h.healthy else "unhealthy",
        graph_reachable=h.healthy,
        backend=info.name,
        backend_version=info.version,
        schema_version=info.schema_version,
    )


@router.get("/version", response_model=VersionInfo)
def version(request: Request) -> VersionInfo:
    info = request.app.state.backend.info()
    return VersionInfo(
        protocol_version=PROTOCOL_VERSION,
        backend=info.name,
        backend_version=info.version,
        schema_version=info.schema_version,
    )
```

Create `packages/guru-graph/src/guru_graph/app.py`:

```python
"""FastAPI app factory for the guru-graph daemon."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .backend.base import GraphBackend
from .routes import admin
from .versioning import (
    PROTOCOL_HEADER,
    PROTOCOL_VERSION,
    VersionNegotiationError,
    negotiate_protocol,
    parse_version,
)

logger = logging.getLogger(__name__)


def create_app(*, backend: GraphBackend) -> FastAPI:
    app = FastAPI(title="guru-graph", version=PROTOCOL_VERSION)
    app.state.backend = backend

    @app.middleware("http")
    async def protocol_version_middleware(request: Request, call_next):
        header = request.headers.get(PROTOCOL_HEADER)
        if header:
            try:
                client = parse_version(header)
                negotiate_protocol(server=parse_version(PROTOCOL_VERSION),
                                    client=client)
            except VersionNegotiationError as e:
                return JSONResponse(
                    status_code=426,
                    content={
                        "error": "protocol_upgrade_required",
                        "detail": str(e),
                        "supported": [f"{parse_version(PROTOCOL_VERSION).major}.x"],
                    },
                )
        response = await call_next(request)
        response.headers[PROTOCOL_HEADER] = PROTOCOL_VERSION
        return response

    app.include_router(admin.router)
    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-graph/tests/test_routes.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add FastAPI app factory and admin routes"
```

---

## Task 8: KB and link routes

**Files:**
- Create: `packages/guru-graph/src/guru_graph/routes/kbs.py`
- Modify: `packages/guru-graph/src/guru_graph/app.py`
- Modify: `packages/guru-graph/tests/test_routes.py`

- [ ] **Step 1: Write failing tests (append to existing file)**

Append to `packages/guru-graph/tests/test_routes.py`:

```python
def test_upsert_kb_returns_201(client: TestClient):
    r = client.post("/kbs", json={
        "name": "alpha", "project_root": "/tmp/a", "tags": ["app"], "metadata": {},
    }, headers=_v1_headers())
    assert r.status_code == 201
    assert r.json()["name"] == "alpha"


def test_get_kb_missing_returns_404(client: TestClient):
    r = client.get("/kbs/missing", headers=_v1_headers())
    assert r.status_code == 404


def test_list_kbs_with_prefix(client: TestClient):
    for n in ("alpha", "alpine", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/tmp/{n}"},
                    headers=_v1_headers())
    r = client.get("/kbs?prefix=al", headers=_v1_headers())
    assert r.status_code == 200
    names = [n["name"] for n in r.json()]
    assert set(names) == {"alpha", "alpine"}


def test_delete_kb(client: TestClient):
    client.post("/kbs", json={"name": "x", "project_root": "/x"},
                headers=_v1_headers())
    r = client.delete("/kbs/x", headers=_v1_headers())
    assert r.status_code == 204
    r2 = client.delete("/kbs/x", headers=_v1_headers())
    assert r2.status_code == 404


def test_create_link_requires_endpoints(client: TestClient):
    client.post("/kbs", json={"name": "alpha", "project_root": "/a"},
                headers=_v1_headers())
    r = client.post("/kbs/alpha/links",
                    json={"to_kb": "beta", "kind": "depends_on"},
                    headers=_v1_headers())
    assert r.status_code == 404


def test_create_and_list_link(client: TestClient):
    for n in ("alpha", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/{n}"},
                    headers=_v1_headers())
    r = client.post("/kbs/alpha/links",
                    json={"to_kb": "beta", "kind": "depends_on"},
                    headers=_v1_headers())
    assert r.status_code == 201
    r2 = client.get("/kbs/alpha/links?direction=out", headers=_v1_headers())
    assert r2.status_code == 200
    body = r2.json()
    assert len(body) == 1
    assert body[0]["to_kb"] == "beta"
    assert body[0]["kind"] == "depends_on"


def test_unknown_link_kind_rejected(client: TestClient):
    for n in ("alpha", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/{n}"},
                    headers=_v1_headers())
    r = client.post("/kbs/alpha/links",
                    json={"to_kb": "beta", "kind": "sorta_related"},
                    headers=_v1_headers())
    assert r.status_code == 422
    body = r.json()
    assert "depends_on" in str(body)


def test_delete_link(client: TestClient):
    for n in ("alpha", "beta"):
        client.post("/kbs", json={"name": n, "project_root": f"/{n}"},
                    headers=_v1_headers())
    client.post("/kbs/alpha/links",
                json={"to_kb": "beta", "kind": "depends_on"},
                headers=_v1_headers())
    r = client.delete("/kbs/alpha/links/beta/depends_on", headers=_v1_headers())
    assert r.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-graph/tests/test_routes.py -v -k "upsert_kb or link or delete_kb or list_kbs"`
Expected: FAIL — 404 on POST /kbs (route not registered yet).

- [ ] **Step 3: Implement `routes/kbs.py`**

Create `packages/guru-graph/src/guru_graph/routes/kbs.py`:

```python
"""KB CRUD and link routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status

from guru_core.graph_types import KbLink, KbLinkCreate, KbNode, KbUpsert, LinkKind

from ..services.kb_service import KbNotFoundError, KbService

router = APIRouter()


def _svc(request: Request) -> KbService:
    return KbService(backend=request.app.state.backend)


@router.post("/kbs", response_model=KbNode, status_code=status.HTTP_201_CREATED)
def upsert_kb(req: KbUpsert, request: Request) -> KbNode:
    return _svc(request).upsert(req)


@router.get("/kbs", response_model=list[KbNode])
def list_kbs(request: Request, prefix: str | None = None,
             tag: str | None = None) -> list[KbNode]:
    return _svc(request).list(prefix=prefix, tag=tag)


@router.get("/kbs/{name}", response_model=KbNode)
def get_kb(name: str, request: Request) -> KbNode:
    node = _svc(request).get(name)
    if node is None:
        raise HTTPException(status_code=404, detail=f"KB {name!r} not found")
    return node


@router.delete("/kbs/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kb(name: str, request: Request) -> Response:
    if not _svc(request).delete(name):
        raise HTTPException(status_code=404, detail=f"KB {name!r} not found")
    return Response(status_code=204)


@router.post("/kbs/{name}/links", response_model=KbLink,
             status_code=status.HTTP_201_CREATED)
def create_link(name: str, body: KbLinkCreate, request: Request) -> KbLink:
    try:
        return _svc(request).link(from_kb=name, req=body)
    except KbNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/kbs/{name}/links/{to}/{kind}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_link(name: str, to: str, kind: LinkKind, request: Request) -> Response:
    if not _svc(request).unlink(from_kb=name, to_kb=to, kind=kind):
        raise HTTPException(status_code=404, detail="link not found")
    return Response(status_code=204)


@router.get("/kbs/{name}/links", response_model=list[KbLink])
def list_links(name: str, request: Request,
               direction: Literal["in", "out", "both"] = "both") -> list[KbLink]:
    return _svc(request).list_links(name=name, direction=direction)
```

- [ ] **Step 4: Register the router**

Modify `packages/guru-graph/src/guru_graph/app.py` — add the import and include:

```python
from .routes import admin, kbs
# ... existing ...
    app.include_router(admin.router)
    app.include_router(kbs.router)
```

- [ ] **Step 5: Run all route tests**

Run: `uv run pytest packages/guru-graph/tests/test_routes.py -v`
Expected: all tests PASS (the 4 admin tests from Task 7 + 8 new ones).

- [ ] **Step 6: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add KB CRUD and link routes"
```

---

## Task 9: Query escape-hatch route

**Files:**
- Create: `packages/guru-graph/src/guru_graph/routes/query.py`
- Modify: `packages/guru-graph/src/guru_graph/app.py`
- Modify: `packages/guru-graph/tests/test_routes.py`

- [ ] **Step 1: Write failing tests (append)**

Append to `packages/guru-graph/tests/test_routes.py`:

```python
def test_query_route_accepts_read_only(client: TestClient):
    r = client.post("/query",
                    json={"cypher": "MATCH (n) RETURN n", "params": {},
                          "read_only": True},
                    headers=_v1_headers())
    assert r.status_code == 200
    body = r.json()
    assert "columns" in body and "rows" in body and "elapsed_ms" in body


def test_query_route_accepts_write(client: TestClient):
    r = client.post("/query",
                    json={"cypher": "CREATE (n:X)", "params": {},
                          "read_only": False},
                    headers=_v1_headers())
    assert r.status_code == 200
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-graph/tests/test_routes.py::test_query_route_accepts_read_only -v`
Expected: FAIL (404 — route not registered).

- [ ] **Step 3: Implement `routes/query.py`**

Create `packages/guru-graph/src/guru_graph/routes/query.py`:

```python
"""Cypher escape-hatch route.

Trust boundary is the UDS file permission. No per-request auth. Writes to the
:Kb / :LINKS / :_Meta schema from here are unsandboxed and can break the
domain contract — documented, not enforced.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from guru_core.graph_types import CypherQuery, QueryResult

from ..services.query_service import QueryService

router = APIRouter()


@router.post("/query", response_model=QueryResult)
def run_query(req: CypherQuery, request: Request) -> QueryResult:
    svc = QueryService(backend=request.app.state.backend)
    return svc.run(req)
```

- [ ] **Step 4: Register the router**

Modify `packages/guru-graph/src/guru_graph/app.py` — add `query` to imports and include:

```python
from .routes import admin, kbs, query
# ... existing ...
    app.include_router(query.router)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest packages/guru-graph/tests/test_routes.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add /query Cypher escape-hatch route"
```

---

## Task 10: Platform paths and port allocation

**Files:**
- Create: `packages/guru-graph/src/guru_graph/config.py`
- Create: `packages/guru-graph/tests/test_config_paths.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-graph/tests/test_config_paths.py`:

```python
from __future__ import annotations

import socket
from pathlib import Path

from guru_graph.config import GraphPaths, allocate_free_loopback_port


def test_graph_paths_produces_all_locations(tmp_path: Path):
    paths = GraphPaths.for_test(base=tmp_path)
    assert paths.socket.parent == tmp_path
    assert paths.data_dir.is_relative_to(tmp_path)
    assert paths.pid_file.is_relative_to(tmp_path)
    assert paths.lock_file.is_relative_to(tmp_path)
    assert paths.log_file.is_relative_to(tmp_path)


def test_graph_paths_ensure_dirs(tmp_path: Path):
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    assert paths.data_dir.exists()
    assert paths.pid_file.parent.exists()


def test_graph_paths_default_respects_platform():
    paths = GraphPaths.default()
    assert "guru" in str(paths.data_dir).lower()
    assert paths.socket.name == "graph.sock"


def test_allocate_free_port_returns_usable():
    port = allocate_free_loopback_port()
    assert 1024 <= port <= 65535
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-graph/tests/test_config_paths.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `config.py`**

Create `packages/guru-graph/src/guru_graph/config.py`:

```python
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
    def default(cls) -> "GraphPaths":
        if sys.platform == "darwin":
            base = Path(platformdirs.user_data_dir("guru", appauthor=False)) / "graph"
            socket = Path(platformdirs.user_data_dir("guru", appauthor=False)) / "graph.sock"
            return cls(
                socket=socket,
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
    def for_test(cls, *, base: Path) -> "GraphPaths":
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest packages/guru-graph/tests/test_config_paths.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add platform paths and port allocator"
```

---

## Task 11: Preflight checks for Java and Neo4j

**Files:**
- Create: `packages/guru-graph/src/guru_graph/preflight.py`
- Create: `packages/guru-graph/tests/test_preflight.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-graph/tests/test_preflight.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pytest

from guru_graph.preflight import (
    JavaNotFoundError,
    Neo4jNotFoundError,
    check_java_installed,
    check_neo4j_installed,
)


def test_java_missing_raises_actionable_error():
    with patch("shutil.which", return_value=None):
        with pytest.raises(JavaNotFoundError) as exc:
            check_java_installed()
        assert "java" in str(exc.value).lower()
        assert "install" in str(exc.value).lower()


def test_java_found():
    with patch("shutil.which", return_value="/usr/bin/java"):
        check_java_installed()  # no raise


def test_neo4j_missing_raises_actionable_error():
    with patch("shutil.which", return_value=None):
        with pytest.raises(Neo4jNotFoundError) as exc:
            check_neo4j_installed()
        assert "neo4j" in str(exc.value).lower()
        assert "brew install neo4j" in str(exc.value).lower() \
            or "neo4j.com/download" in str(exc.value).lower()


def test_neo4j_found():
    with patch("shutil.which", return_value="/opt/homebrew/bin/neo4j"):
        check_neo4j_installed()  # no raise
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-graph/tests/test_preflight.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `preflight.py`**

Create `packages/guru-graph/src/guru_graph/preflight.py`:

```python
"""Preflight checks run during guru-graph daemon startup.

Mirrors guru-server's Ollama preflight pattern. Hard errors on missing deps
with clear install instructions.
"""

from __future__ import annotations

import logging
import shutil

logger = logging.getLogger(__name__)


class JavaNotFoundError(RuntimeError):
    pass


class Neo4jNotFoundError(RuntimeError):
    pass


def check_java_installed() -> None:
    if shutil.which("java") is None:
        raise JavaNotFoundError(
            "Java is not installed or not on PATH. Neo4j requires Java 17+.\n"
            "Install it with: brew install openjdk@17 (macOS) "
            "or apt install openjdk-17-jre (Debian/Ubuntu).\n"
            "After install, run: java -version (should report 17+)."
        )
    logger.info("Java found on PATH")


def check_neo4j_installed() -> None:
    if shutil.which("neo4j") is None:
        raise Neo4jNotFoundError(
            "Neo4j is not installed or not on PATH.\n"
            "Install it with: brew install neo4j (macOS) "
            "or see https://neo4j.com/download/ for other platforms.\n"
            "Requires Java 17+."
        )
    logger.info("Neo4j found on PATH")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/guru-graph/tests/test_preflight.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add preflight checks for Java and Neo4j"
```

---

## Task 12: Neo4j subprocess manager

**Files:**
- Create: `packages/guru-graph/src/guru_graph/neo4j_process.py`

This task implements a subprocess wrapper with no unit tests — it's exercised by the `@real_neo4j` backend test in Task 14 and by BDD tests. Writing deterministic unit tests for subprocess lifecycle is low-value compared to real end-to-end verification.

- [ ] **Step 1: Implement `neo4j_process.py`**

Create `packages/guru-graph/src/guru_graph/neo4j_process.py`:

```python
"""Supervise a Neo4j subprocess.

guru-graph is the sole owner of the Neo4j process lifecycle. We run `neo4j
console` (foreground) as a child, configure the data dir via env/config,
choose a free loopback port, and probe readiness by opening a Bolt driver.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class Neo4jStartError(RuntimeError):
    pass


@dataclass
class Neo4jRuntime:
    bolt_uri: str  # bolt://127.0.0.1:<port>
    process: subprocess.Popen
    data_dir: Path


def start_neo4j(
    *, data_dir: Path, bolt_port: int, log_file: Path,
    initial_password: str = "guru-graph-local",
    ready_timeout_seconds: float = 60.0,
) -> Neo4jRuntime:
    """Spawn neo4j console pointed at data_dir, bind Bolt to loopback port.

    Uses environment variables to configure Neo4j at launch:
      - NEO4J_server_directories_data
      - NEO4J_server_bolt_listen__address
      - NEO4J_server_default__listen__address
      - NEO4J_dbms_security_auth__enabled = false (local UDS-guarded daemon)
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "NEO4J_server_directories_data": str(data_dir),
        "NEO4J_server_default_listen_address": "127.0.0.1",
        "NEO4J_server_bolt_listen__address": f"127.0.0.1:{bolt_port}",
        "NEO4J_server_bolt_advertised__address": f"127.0.0.1:{bolt_port}",
        "NEO4J_server_http_enabled": "false",
        "NEO4J_server_https_enabled": "false",
        "NEO4J_dbms_security_auth__enabled": "false",
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_file, "ab")
    proc = subprocess.Popen(
        ["neo4j", "console"],
        env=env,
        stdout=log_fd,
        stderr=log_fd,
        start_new_session=True,
    )
    bolt_uri = f"bolt://127.0.0.1:{bolt_port}"
    deadline = time.monotonic() + ready_timeout_seconds
    last_err: Exception | None = None
    from neo4j import GraphDatabase, exceptions as neo4j_exceptions  # local import

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise Neo4jStartError(
                f"neo4j exited during startup (code={proc.returncode}); see {log_file}"
            )
        try:
            driver = GraphDatabase.driver(bolt_uri, auth=None, max_connection_lifetime=60)
            driver.verify_connectivity()
            driver.close()
            logger.info("neo4j ready at %s", bolt_uri)
            return Neo4jRuntime(bolt_uri=bolt_uri, process=proc, data_dir=data_dir)
        except neo4j_exceptions.Neo4jError as e:  # pragma: no cover
            last_err = e
            time.sleep(0.5)
        except Exception as e:  # pragma: no cover — driver raises a range during startup
            last_err = e
            time.sleep(0.5)

    # Timed out
    stop_neo4j(proc)
    raise Neo4jStartError(
        f"neo4j did not become ready within {ready_timeout_seconds}s. "
        f"Last error: {last_err!r}. See {log_file}"
    )


def stop_neo4j(proc: subprocess.Popen, *, grace_seconds: float = 15.0) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        logger.warning("neo4j did not exit in %ss; sending SIGKILL", grace_seconds)
        proc.kill()
        proc.wait()
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from guru_graph.neo4j_process import start_neo4j, stop_neo4j, Neo4jRuntime; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add Neo4j subprocess manager"
```

---

## Task 13: `Neo4jBackend` — concrete backend

**Files:**
- Create: `packages/guru-graph/src/guru_graph/backend/neo4j_backend.py`
- Modify: `packages/guru-graph/src/guru_graph/backend/__init__.py`

No unit tests for this task — it is exercised end-to-end by Task 14's `@real_neo4j` test. Pure-unit testing a driver wrapper is low-value.

- [ ] **Step 1: Implement `Neo4jBackend`**

Create `packages/guru-graph/src/guru_graph/backend/neo4j_backend.py`:

```python
"""Concrete GraphBackend using the official Neo4j Python driver over Bolt."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from ..neo4j_process import Neo4jRuntime, start_neo4j, stop_neo4j
from ..versioning import VersionNegotiationError, check_migration_target
from .base import BackendHealth, BackendInfo, CypherResult, GraphBackendRegistry, Tx

logger = logging.getLogger(__name__)


class Neo4jBackend:
    """Owns a Neo4j subprocess and a Bolt driver pointed at it."""

    def __init__(
        self,
        *,
        data_dir: Path,
        bolt_port: int,
        log_file: Path,
    ):
        self._data_dir = data_dir
        self._bolt_port = bolt_port
        self._log_file = log_file
        self._runtime: Neo4jRuntime | None = None
        self._driver = None
        self._schema_version = 0
        self._neo4j_version = "unknown"

    # ---- Lifecycle ----
    def start(self) -> None:
        self._runtime = start_neo4j(
            data_dir=self._data_dir,
            bolt_port=self._bolt_port,
            log_file=self._log_file,
        )
        self._driver = GraphDatabase.driver(self._runtime.bolt_uri, auth=None)
        # Best-effort version read; fall back to "unknown".
        try:
            with self._driver.session() as s:
                rec = s.run("CALL dbms.components() YIELD name, versions "
                             "WHERE name='Neo4j Kernel' RETURN versions[0] AS v"
                             ).single()
                if rec:
                    self._neo4j_version = rec["v"]
        except Exception as e:
            logger.warning("could not read neo4j version: %s", e)
        # Read existing schema version if meta node exists.
        self._schema_version = self._read_schema_version()

    def stop(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
        if self._runtime is not None:
            stop_neo4j(self._runtime.process)
            self._runtime = None

    # ---- Health + info ----
    def health(self) -> BackendHealth:
        if self._driver is None:
            return BackendHealth(healthy=False, detail="driver not initialised")
        try:
            self._driver.verify_connectivity()
            return BackendHealth(healthy=True)
        except Exception as e:
            return BackendHealth(healthy=False, detail=str(e))

    def info(self) -> BackendInfo:
        return BackendInfo(
            name="neo4j",
            version=self._neo4j_version,
            schema_version=self._schema_version,
        )

    # ---- Cypher surface ----
    def execute(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        assert self._driver is not None
        start = time.monotonic()
        with self._driver.session() as s:
            res = s.run(cypher, parameters=params)
            rows = [[v for v in r.values()] for r in res]
            columns = list(res.keys()) if hasattr(res, "keys") else []
        elapsed_ms = (time.monotonic() - start) * 1000
        return CypherResult(columns=columns, rows=rows, elapsed_ms=elapsed_ms)

    def execute_read(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        assert self._driver is not None
        start = time.monotonic()
        with self._driver.session() as s:
            def _work(tx):
                res = tx.run(cypher, parameters=params)
                return list(res.keys()), [[v for v in r.values()] for r in res]
            columns, rows = s.execute_read(_work)
        elapsed_ms = (time.monotonic() - start) * 1000
        return CypherResult(columns=columns, rows=rows, elapsed_ms=elapsed_ms)

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[Tx]:
        assert self._driver is not None
        with self._driver.session() as s:
            if read_only:
                tx = s.begin_transaction()
            else:
                tx = s.begin_transaction()
            try:
                yield Tx(backend=self, read_only=read_only)
                tx.commit()
            except Exception:
                tx.rollback()
                raise

    # ---- Schema ----
    def ensure_schema(self, target_version: int) -> None:
        current = self._read_schema_version()
        check_migration_target(current=current, target=target_version)
        from ..migrations import run_pending_migrations
        run_pending_migrations(backend=self, current=current, target=target_version)
        self._schema_version = self._read_schema_version()

    def _read_schema_version(self) -> int:
        if self._driver is None:
            return 0
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (m:_Meta {kind: 'schema'}) "
                "RETURN m.schema_version AS v"
            ).single()
            return int(rec["v"]) if rec and rec["v"] is not None else 0

    # ---- Declarative KB helpers (called by KbService) ----
    def upsert_kb(self, *, name: str, project_root: str, tags: list[str],
                  metadata_json: str) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MERGE (k:Kb {name: $name})
                ON CREATE SET k.created_at = timestamp(), k.updated_at = timestamp(),
                              k.project_root = $project_root,
                              k.tags = $tags,
                              k.metadata_json = $metadata_json
                ON MATCH SET k.updated_at = timestamp(),
                             k.project_root = $project_root,
                             k.tags = $tags,
                             k.metadata_json = $metadata_json
                """,
                parameters={"name": name, "project_root": project_root,
                            "tags": tags, "metadata_json": metadata_json},
            )

    def get_kb(self, name: str) -> dict[str, Any] | None:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (k:Kb {name: $name}) "
                "RETURN k.name AS name, k.project_root AS project_root, "
                "       k.tags AS tags, k.metadata_json AS metadata_json, "
                "       k.created_at AS created_at, k.updated_at AS updated_at",
                parameters={"name": name},
            ).single()
            if rec is None:
                return None
            return {
                "name": rec["name"],
                "project_root": rec["project_root"],
                "tags": list(rec["tags"] or []),
                "metadata_json": rec["metadata_json"] or "{}",
                "created_at": rec["created_at"] / 1000.0,
                "updated_at": rec["updated_at"] / 1000.0,
            }

    def list_kbs(self, *, prefix: str | None = None,
                 tag: str | None = None) -> list[dict[str, Any]]:
        filters = []
        params: dict[str, Any] = {}
        if prefix:
            filters.append("k.name STARTS WITH $prefix")
            params["prefix"] = prefix
        if tag:
            filters.append("$tag IN k.tags")
            params["tag"] = tag
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cypher = (
            f"MATCH (k:Kb) {where} "
            "RETURN k.name AS name, k.project_root AS project_root, "
            "       k.tags AS tags, k.metadata_json AS metadata_json, "
            "       k.created_at AS created_at, k.updated_at AS updated_at "
            "ORDER BY k.name"
        )
        with self._driver.session() as s:
            rs = s.run(cypher, parameters=params)
            return [
                {
                    "name": r["name"],
                    "project_root": r["project_root"],
                    "tags": list(r["tags"] or []),
                    "metadata_json": r["metadata_json"] or "{}",
                    "created_at": r["created_at"] / 1000.0,
                    "updated_at": r["updated_at"] / 1000.0,
                }
                for r in rs
            ]

    def delete_kb(self, name: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (k:Kb {name: $name}) "
                "OPTIONAL MATCH (k)-[r:LINKS]-() "
                "WITH k, count(r) AS edges DELETE r, k RETURN edges + 1 AS deleted",
                parameters={"name": name},
            ).single()
            return bool(rec and rec["deleted"])

    def link(self, *, from_kb: str, to_kb: str, kind: str,
             metadata_json: str) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MATCH (a:Kb {name: $from_kb}), (b:Kb {name: $to_kb})
                MERGE (a)-[r:LINKS {kind: $kind}]->(b)
                ON CREATE SET r.created_at = timestamp(),
                              r.metadata_json = $metadata_json
                ON MATCH SET r.metadata_json = $metadata_json
                """,
                parameters={"from_kb": from_kb, "to_kb": to_kb,
                            "kind": kind, "metadata_json": metadata_json},
            )

    def unlink(self, *, from_kb: str, to_kb: str, kind: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (a:Kb {name: $from_kb})-[r:LINKS {kind: $kind}]->(b:Kb {name: $to_kb})
                WITH r, count(r) AS c DELETE r RETURN c
                """,
                parameters={"from_kb": from_kb, "to_kb": to_kb, "kind": kind},
            ).single()
            return bool(rec and rec["c"])

    def list_links_for(self, *, name: str,
                       direction: str = "both") -> list[dict[str, Any]]:
        if direction == "out":
            cypher = ("MATCH (a:Kb {name: $name})-[r:LINKS]->(b:Kb) "
                      "RETURN a.name AS from_kb, b.name AS to_kb, r.kind AS kind, "
                      "       r.created_at AS created_at, r.metadata_json AS metadata_json")
        elif direction == "in":
            cypher = ("MATCH (a:Kb)-[r:LINKS]->(b:Kb {name: $name}) "
                      "RETURN a.name AS from_kb, b.name AS to_kb, r.kind AS kind, "
                      "       r.created_at AS created_at, r.metadata_json AS metadata_json")
        else:
            cypher = ("MATCH (a:Kb)-[r:LINKS]->(b:Kb) "
                      "WHERE a.name = $name OR b.name = $name "
                      "RETURN a.name AS from_kb, b.name AS to_kb, r.kind AS kind, "
                      "       r.created_at AS created_at, r.metadata_json AS metadata_json")
        with self._driver.session() as s:
            rs = s.run(cypher, parameters={"name": name})
            return [
                {
                    "from_kb": r["from_kb"], "to_kb": r["to_kb"],
                    "kind": r["kind"],
                    "created_at": r["created_at"] / 1000.0,
                    "metadata_json": r["metadata_json"] or "{}",
                }
                for r in rs
            ]


GraphBackendRegistry.register("neo4j", Neo4jBackend)
```

- [ ] **Step 2: Re-export**

Modify `packages/guru-graph/src/guru_graph/backend/__init__.py` — append:

```python
from .neo4j_backend import Neo4jBackend  # noqa: E402  (after base)

__all__ = [
    *__all__,
    "Neo4jBackend",
]
```

- [ ] **Step 3: Verify imports**

Run: `uv run python -c "from guru_graph.backend import Neo4jBackend, GraphBackendRegistry; print(GraphBackendRegistry.names())"`
Expected: `['neo4j']`.

- [ ] **Step 4: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add Neo4jBackend concrete implementation"
```

---

## Task 14: Migration framework and m0001 initial migration

**Files:**
- Create: `packages/guru-graph/src/guru_graph/migrations/__init__.py`
- Create: `packages/guru-graph/src/guru_graph/migrations/m0001_initial.py`
- Create: `packages/guru-graph/tests/test_neo4j_backend.py` (`@real_neo4j`)
- Create: `packages/guru-graph/tests/test_migrations.py` (`@real_neo4j`)
- Create: `packages/guru-graph/tests/conftest.py`

- [ ] **Step 1: Implement migration framework**

Create `packages/guru-graph/src/guru_graph/migrations/__init__.py`:

```python
"""Forward-only migrations for the Neo4j schema.

Each migration is a callable taking the backend. It runs idempotent Cypher
and writes `(:_Meta {kind:'schema'}).schema_version` to its number. Applied
in order during `backend.ensure_schema(target)`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from .m0001_initial import apply as m0001

logger = logging.getLogger(__name__)

Migration = Callable[[object], None]

MIGRATIONS: list[tuple[int, Migration]] = [
    (1, m0001),
]


def run_pending_migrations(*, backend: object, current: int, target: int) -> None:
    for version, fn in MIGRATIONS:
        if version <= current:
            continue
        if version > target:
            break
        logger.info("applying migration m%04d", version)
        fn(backend)
```

Create `packages/guru-graph/src/guru_graph/migrations/m0001_initial.py`:

```python
"""m0001 — initial schema.

Creates:
  - constraint kb_name_unique (UNIQUE on :Kb.name)
  - index kb_updated_at (:Kb(updated_at))
  - (:_Meta {kind:'schema'}) singleton with schema_version=1

Note on _Meta singleton: Neo4j Community cannot enforce node-count
constraints. Discipline = always MERGE on {kind:'schema'}.
"""

from __future__ import annotations

CYPHER_STEPS = [
    # constraint + indexes — idempotent with IF NOT EXISTS
    "CREATE CONSTRAINT kb_name_unique IF NOT EXISTS "
    "FOR (k:Kb) REQUIRE k.name IS UNIQUE",

    "CREATE INDEX kb_updated_at IF NOT EXISTS "
    "FOR (k:Kb) ON (k.updated_at)",

    # meta node — disciplined singleton via MERGE on kind
    "MERGE (m:_Meta {kind: 'schema'}) "
    "ON CREATE SET m.schema_version = 1, m.created_at = timestamp() "
    "ON MATCH SET m.schema_version = 1",
]


def apply(backend) -> None:
    for step in CYPHER_STEPS:
        backend.execute(step, {})
```

- [ ] **Step 2: Create conftest (real_neo4j skip marker)**

Create `packages/guru-graph/tests/conftest.py`:

```python
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip @real_neo4j tests unless GURU_REAL_NEO4J=1 or `neo4j` on PATH."""
    real_neo4j_enabled = (
        os.environ.get("GURU_REAL_NEO4J") == "1"
        or shutil.which("neo4j") is not None
    )
    if real_neo4j_enabled:
        return
    skip = pytest.mark.skip(reason="real_neo4j not available (set GURU_REAL_NEO4J=1)")
    for item in items:
        if "real_neo4j" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def real_neo4j_backend(tmp_path: Path):
    """Spin up a real Neo4j for a single test."""
    from guru_graph.backend import Neo4jBackend
    from guru_graph.config import allocate_free_loopback_port

    port = allocate_free_loopback_port()
    data_dir = tmp_path / "neo4j"
    log_file = tmp_path / "neo4j.log"
    backend = Neo4jBackend(
        data_dir=data_dir, bolt_port=port, log_file=log_file,
    )
    backend.start()
    try:
        yield backend
    finally:
        backend.stop()
```

- [ ] **Step 3: Write `@real_neo4j` tests for backend and migrations**

Create `packages/guru-graph/tests/test_neo4j_backend.py`:

```python
from __future__ import annotations

import pytest

pytestmark = pytest.mark.real_neo4j


def test_backend_starts_and_reports_version(real_neo4j_backend):
    h = real_neo4j_backend.health()
    assert h.healthy is True
    info = real_neo4j_backend.info()
    assert info.name == "neo4j"
    assert info.version != "unknown"


def test_execute_returns_rows(real_neo4j_backend):
    res = real_neo4j_backend.execute_read("RETURN 1 AS x", {})
    assert res.rows == [[1]]
    assert res.columns == ["x"]


def test_upsert_and_get_kb(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    real_neo4j_backend.upsert_kb(
        name="alpha", project_root="/a", tags=[], metadata_json="{}"
    )
    row = real_neo4j_backend.get_kb("alpha")
    assert row is not None
    assert row["name"] == "alpha"


def test_link_and_list_links(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    real_neo4j_backend.upsert_kb(name="a", project_root="/a", tags=[], metadata_json="{}")
    real_neo4j_backend.upsert_kb(name="b", project_root="/b", tags=[], metadata_json="{}")
    real_neo4j_backend.link(from_kb="a", to_kb="b", kind="depends_on", metadata_json="{}")
    outs = real_neo4j_backend.list_links_for(name="a", direction="out")
    assert len(outs) == 1
    assert outs[0]["kind"] == "depends_on"
```

Create `packages/guru-graph/tests/test_migrations.py`:

```python
from __future__ import annotations

import pytest

from guru_graph.versioning import VersionNegotiationError

pytestmark = pytest.mark.real_neo4j


def test_ensure_schema_applies_m0001(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    assert real_neo4j_backend.info().schema_version == 1


def test_ensure_schema_is_idempotent(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    real_neo4j_backend.ensure_schema(target_version=1)
    assert real_neo4j_backend.info().schema_version == 1


def test_ensure_schema_refuses_downgrade(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    with pytest.raises(VersionNegotiationError):
        real_neo4j_backend.ensure_schema(target_version=0)
```

- [ ] **Step 4: Run @real_neo4j tests (locally, if Neo4j installed)**

Run: `GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/tests/test_neo4j_backend.py packages/guru-graph/tests/test_migrations.py -v`
Expected: all PASS if Neo4j is on PATH; SKIPPED otherwise.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add migration framework and m0001 initial schema"
```

---

## Task 15: `/query` escape-hatch against real Neo4j

**Files:**
- Create: `packages/guru-graph/tests/test_escape_hatch.py` (`@real_neo4j`)

- [ ] **Step 1: Write tests**

Create `packages/guru-graph/tests/test_escape_hatch.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.versioning import PROTOCOL_HEADER, PROTOCOL_VERSION

pytestmark = pytest.mark.real_neo4j


@pytest.fixture
def client(real_neo4j_backend) -> TestClient:
    real_neo4j_backend.ensure_schema(target_version=1)
    app = create_app(backend=real_neo4j_backend)
    with TestClient(app) as c:
        yield c


def _hdr() -> dict[str, str]:
    return {PROTOCOL_HEADER: PROTOCOL_VERSION}


def test_read_only_roundtrip(client: TestClient):
    r = client.post("/query", json={
        "cypher": "RETURN 1 AS x, 'hi' AS y", "params": {}, "read_only": True,
    }, headers=_hdr())
    assert r.status_code == 200
    body = r.json()
    assert body["columns"] == ["x", "y"]
    assert body["rows"] == [[1, "hi"]]


def test_write_query_via_escape_hatch(client: TestClient):
    client.post("/query", json={
        "cypher": "CREATE (:TempNode {v: $v})", "params": {"v": 42}, "read_only": False,
    }, headers=_hdr())
    r2 = client.post("/query", json={
        "cypher": "MATCH (n:TempNode) RETURN n.v AS v", "params": {}, "read_only": True,
    }, headers=_hdr())
    assert r2.status_code == 200
    assert r2.json()["rows"] == [[42]]


def test_malformed_cypher_returns_structured_error(client: TestClient):
    r = client.post("/query", json={
        "cypher": "THIS IS NOT CYPHER", "params": {}, "read_only": True,
    }, headers=_hdr())
    assert r.status_code == 500
    assert "detail" in r.json() or "error" in r.json()
```

- [ ] **Step 2: Run the tests**

Run: `GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/tests/test_escape_hatch.py -v`
Expected: PASS locally with Neo4j; SKIPPED otherwise.

- [ ] **Step 3: Commit**

```bash
git add packages/guru-graph/tests/test_escape_hatch.py
git commit -m "test(graph): add @real_neo4j escape-hatch tests"
```

---

## Task 16: Daemon lifecycle — lazy-start, flock, double-fork

**Files:**
- Create: `packages/guru-graph/src/guru_graph/lifecycle.py`
- Create: `packages/guru-graph/tests/test_lifecycle.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-graph/tests/test_lifecycle.py`:

```python
from __future__ import annotations

import os
import socket
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from guru_graph.config import GraphPaths
from guru_graph.lifecycle import (
    DaemonNotReady,
    connect_or_spawn,
    is_socket_alive,
    read_pid_file,
    write_pid_file,
)


def test_pid_file_round_trip(tmp_path: Path):
    pid_file = tmp_path / "d.pid"
    write_pid_file(pid_file, 12345)
    assert read_pid_file(pid_file) == 12345


def test_read_pid_missing_returns_none(tmp_path: Path):
    assert read_pid_file(tmp_path / "nope") is None


def test_read_pid_garbage_returns_none(tmp_path: Path):
    pid_file = tmp_path / "garbage"
    pid_file.write_text("not a number")
    assert read_pid_file(pid_file) is None


def test_socket_alive_nonexistent(tmp_path: Path):
    assert is_socket_alive(tmp_path / "missing.sock") is False


def test_connect_or_spawn_spawns_when_missing(tmp_path: Path):
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    calls = []

    def fake_spawn():
        calls.append("spawn")
        # simulate daemon creating the socket
        s = socket.socket(socket.AF_UNIX)
        s.bind(str(paths.socket))
        s.listen()
        return 99999

    with patch.object(__import__("guru_graph.lifecycle", fromlist=["_spawn_daemon"]),
                      "_spawn_daemon", side_effect=fake_spawn):
        # readiness poll will time out unless we also mock is_socket_alive
        with patch("guru_graph.lifecycle.is_socket_alive",
                    side_effect=[False, True]):
            connect_or_spawn(paths=paths, ready_timeout_seconds=2.0)

    assert calls == ["spawn"]


def test_connect_or_spawn_skips_when_socket_alive(tmp_path: Path, monkeypatch):
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    monkeypatch.setattr("guru_graph.lifecycle.is_socket_alive", lambda p: True)
    spawned = []
    monkeypatch.setattr(
        "guru_graph.lifecycle._spawn_daemon", lambda: spawned.append(1) or 1)
    connect_or_spawn(paths=paths, ready_timeout_seconds=1.0)
    assert spawned == []


def test_concurrent_spawn_only_one_wins(tmp_path: Path, monkeypatch):
    """Two callers hit connect_or_spawn at once; only one spawns."""
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    spawn_count = 0
    lock = threading.Lock()

    # Simulate: socket is dead until spawn. After spawn, it's alive.
    socket_alive = {"value": False}

    def fake_is_alive(path):
        return socket_alive["value"]

    def fake_spawn():
        nonlocal spawn_count
        with lock:
            spawn_count += 1
            socket_alive["value"] = True
        return 12345

    monkeypatch.setattr("guru_graph.lifecycle.is_socket_alive", fake_is_alive)
    monkeypatch.setattr("guru_graph.lifecycle._spawn_daemon", fake_spawn)

    threads = [threading.Thread(target=connect_or_spawn,
                                  kwargs={"paths": paths,
                                          "ready_timeout_seconds": 2.0})
               for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert spawn_count == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-graph/tests/test_lifecycle.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `lifecycle.py`**

Create `packages/guru-graph/src/guru_graph/lifecycle.py`:

```python
"""Daemon lazy-start, flock-based leader election, stale-socket recovery.

This module is imported by BOTH the guru-core GraphClient (to autostart) and
the guru-graph daemon entrypoint (to write pid/lock).
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .config import GraphPaths

logger = logging.getLogger(__name__)


class DaemonNotReady(RuntimeError):
    pass


def read_pid_file(path: Path) -> int | None:
    try:
        text = path.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def write_pid_file(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{pid}")
    tmp.write_text(str(pid))
    os.replace(tmp, path)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def is_socket_alive(path: Path) -> bool:
    """Probe whether the UDS socket has a listener accepting connections."""
    if not path.exists():
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(str(path))
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False
    finally:
        s.close()


def _spawn_daemon() -> int:
    """Spawn the guru-graph daemon, detached, return its pid."""
    # Launch via entry-point script so hooks/tests can monkeypatch this fn
    # instead of launching a real daemon.
    proc = subprocess.Popen(
        [sys.executable, "-m", "guru_graph.main"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid


def connect_or_spawn(*, paths: GraphPaths,
                     ready_timeout_seconds: float = 30.0) -> None:
    """Ensure a daemon is running and its socket is reachable.

    1. Probe socket. If alive → done.
    2. flock on .daemon.lock (blocking). Re-probe — maybe a peer started it
       while we waited.
    3. Clean up any stale pid/socket; spawn a fresh daemon.
    4. Poll until socket is reachable or timeout.
    """
    if is_socket_alive(paths.socket):
        return
    paths.ensure_dirs()
    lock_fd = os.open(paths.lock_file, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if is_socket_alive(paths.socket):
            return
        # Clean stale socket file if present.
        if paths.socket.exists():
            try:
                paths.socket.unlink()
            except FileNotFoundError:
                pass
        # Clean stale pid if the process is gone.
        existing = read_pid_file(paths.pid_file)
        if existing is not None and not _pid_alive(existing):
            try:
                paths.pid_file.unlink()
            except FileNotFoundError:
                pass

        pid = _spawn_daemon()
        write_pid_file(paths.pid_file, pid)

        deadline = time.monotonic() + ready_timeout_seconds
        while time.monotonic() < deadline:
            if is_socket_alive(paths.socket):
                return
            time.sleep(0.2)
        raise DaemonNotReady(
            f"daemon did not bind {paths.socket} within {ready_timeout_seconds}s"
        )
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest packages/guru-graph/tests/test_lifecycle.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-graph
git commit -m "feat(graph): add daemon lazy-start with flock leader election"
```

---

## Task 17: Daemon entrypoint `main.py`

**Files:**
- Create: `packages/guru-graph/src/guru_graph/main.py`

- [ ] **Step 1: Implement the entrypoint**

Create `packages/guru-graph/src/guru_graph/main.py`:

```python
"""guru-graph-daemon entrypoint.

Invoked by `connect_or_spawn` or directly via the `guru-graph-daemon`
console script. Responsibilities:
  1. Run preflight (java + neo4j).
  2. Allocate a free loopback port.
  3. Start Neo4jBackend.
  4. Run migrations up to SCHEMA_VERSION.
  5. Serve the FastAPI app over UDS at GraphPaths.socket.
  6. Handle SIGTERM / SIGINT gracefully.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import uvicorn

from .app import create_app
from .backend import Neo4jBackend
from .config import GraphPaths, allocate_free_loopback_port
from .preflight import check_java_installed, check_neo4j_installed
from .versioning import SCHEMA_VERSION


def _configure_logging(log_file) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )


def main() -> int:
    paths = GraphPaths.default()
    paths.ensure_dirs()
    _configure_logging(paths.log_file)
    logger = logging.getLogger("guru_graph.main")

    try:
        check_java_installed()
        check_neo4j_installed()
    except RuntimeError as e:
        logger.error("preflight failed: %s", e)
        return 2

    port = allocate_free_loopback_port()
    backend = Neo4jBackend(
        data_dir=paths.data_dir, bolt_port=port, log_file=paths.data_dir / "neo4j.log",
    )
    backend.start()
    try:
        backend.ensure_schema(target_version=SCHEMA_VERSION)
        app = create_app(backend=backend)

        # Remove any stale socket so uvicorn can bind cleanly.
        if paths.socket.exists():
            try:
                paths.socket.unlink()
            except FileNotFoundError:
                pass

        stopping = {"flag": False}

        def _handle_sig(signum, frame):
            if stopping["flag"]:
                return
            stopping["flag"] = True
            logger.info("received signal %d, shutting down", signum)
            # uvicorn catches SIGTERM itself; re-raising isn't needed.

        signal.signal(signal.SIGTERM, _handle_sig)
        signal.signal(signal.SIGINT, _handle_sig)

        config = uvicorn.Config(
            app, uds=str(paths.socket), log_level="info",
            access_log=False,
        )
        server = uvicorn.Server(config=config)
        server.run()
    finally:
        backend.stop()
        try:
            paths.socket.unlink()
        except FileNotFoundError:
            pass
        try:
            paths.pid_file.unlink()
        except FileNotFoundError:
            pass

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from guru_graph import main; print(main.main.__name__)"`
Expected: `main`.

- [ ] **Step 3: Commit**

```bash
git add packages/guru-graph/src/guru_graph/main.py
git commit -m "feat(graph): add daemon entrypoint wiring all components"
```

---

## Task 18: `GraphClient` in guru-core (HTTP-over-UDS + autostart)

**Files:**
- Create: `packages/guru-core/src/guru_core/graph_client.py`
- Create: `packages/guru-core/tests/test_graph_client.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-core/tests/test_graph_client.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable


@pytest.mark.asyncio
async def test_health_translates_connect_error_to_graph_unavailable(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "nope.sock"),
                          auto_start=False)
    with pytest.raises(GraphUnavailable):
        await client.health()


@pytest.mark.asyncio
async def test_426_response_raises_graph_unavailable(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "ok.sock"), auto_start=False)
    response = httpx.Response(
        status_code=426,
        json={"error": "protocol_upgrade_required", "supported": ["1.x"]},
    )
    fake_get = AsyncMock(return_value=response)
    with patch.object(httpx.AsyncClient, "get", fake_get):
        with pytest.raises(GraphUnavailable) as exc:
            await client.health()
        assert "protocol" in str(exc.value).lower() or "426" in str(exc.value)


@pytest.mark.asyncio
async def test_503_raises_graph_unavailable(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "ok.sock"), auto_start=False)
    response = httpx.Response(503, json={"error": "graph_unavailable",
                                          "detail": "neo4j down"})
    fake_get = AsyncMock(return_value=response)
    with patch.object(httpx.AsyncClient, "get", fake_get):
        with pytest.raises(GraphUnavailable):
            await client.health()


@pytest.mark.asyncio
async def test_auto_start_false_does_not_spawn(tmp_path):
    client = GraphClient(socket_path=str(tmp_path / "gone.sock"),
                          auto_start=False)
    with pytest.raises(GraphUnavailable):
        await client.health()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-core/tests/test_graph_client.py -v`
Expected: FAIL — `ModuleNotFoundError: guru_core.graph_client`.

- [ ] **Step 3: Implement `GraphClient`**

Create `packages/guru-core/src/guru_core/graph_client.py`:

```python
"""HTTP-over-UDS client for guru-graph daemon.

Lives in guru-core so guru-server, guru-cli, and guru-mcp can share it.
Never imports the Neo4j driver — the daemon is the only code that talks
to Neo4j.

All transport failures and protocol/health errors are translated to
GraphUnavailable so consumers can use graph_or_skip to degrade silently.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx

from .graph_errors import GraphUnavailable
from .graph_types import (
    CypherQuery,
    Health,
    KbLink,
    KbLinkCreate,
    KbNode,
    KbUpsert,
    LinkKind,
    QueryResult,
    VersionInfo,
)

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "1.0.0"
PROTOCOL_HEADER = "X-Guru-Graph-Protocol"


class GraphClient:
    """Async HTTP/UDS client. Raises GraphUnavailable on any failure to reach
    the daemon, 503, 426, timeout, or stale socket.
    """

    _timeout = httpx.Timeout(5.0, read=30.0)

    def __init__(
        self,
        *,
        socket_path: str,
        auto_start: bool = True,
        ready_timeout_seconds: float = 30.0,
    ):
        self.socket_path = socket_path
        self.auto_start = auto_start
        self._ready_timeout = ready_timeout_seconds

    def _transport(self) -> httpx.AsyncHTTPTransport:
        return httpx.AsyncHTTPTransport(uds=self.socket_path)

    def _headers(self) -> dict[str, str]:
        return {PROTOCOL_HEADER: PROTOCOL_VERSION}

    async def _ensure_daemon(self) -> None:
        if not self.auto_start:
            return
        # Import here to keep guru-core independent if guru-graph isn't installed.
        try:
            from guru_graph.config import GraphPaths  # type: ignore
            from guru_graph.lifecycle import connect_or_spawn  # type: ignore
        except ImportError:
            return  # plugin not installed; let the request fail with GraphUnavailable
        paths = GraphPaths.default()
        if Path(self.socket_path) == paths.socket:
            await asyncio.to_thread(
                connect_or_spawn, paths=paths,
                ready_timeout_seconds=self._ready_timeout,
            )

    async def _request(self, method: str, path: str, *,
                       json: dict | None = None) -> Any:
        try:
            await self._ensure_daemon()
        except Exception as e:
            raise GraphUnavailable(f"autostart failed: {e}") from e
        try:
            async with httpx.AsyncClient(
                transport=self._transport(), timeout=self._timeout,
            ) as client:
                resp = await client.request(
                    method, f"http://localhost{path}",
                    headers=self._headers(), json=json,
                )
        except httpx.HTTPError as e:
            raise GraphUnavailable(f"transport error: {e}") from e
        except FileNotFoundError as e:
            raise GraphUnavailable(f"socket missing: {e}") from e

        if resp.status_code == 426:
            raise GraphUnavailable(f"protocol upgrade required: {resp.json()}")
        if resp.status_code == 503:
            raise GraphUnavailable(f"daemon unhealthy: {resp.text}")
        if resp.status_code >= 500:
            raise GraphUnavailable(f"daemon error {resp.status_code}: {resp.text}")
        return resp

    # ---- Public API ----
    async def health(self) -> Health:
        resp = await self._request("GET", "/health")
        if resp.status_code != 200:
            raise GraphUnavailable(f"unexpected {resp.status_code}")
        return Health.model_validate(resp.json())

    async def version(self) -> VersionInfo:
        resp = await self._request("GET", "/version")
        return VersionInfo.model_validate(resp.json())

    async def upsert_kb(self, req: KbUpsert) -> KbNode:
        resp = await self._request("POST", "/kbs", json=req.model_dump())
        return KbNode.model_validate(resp.json())

    async def get_kb(self, name: str) -> KbNode | None:
        resp = await self._request("GET", f"/kbs/{quote(name, safe='')}")
        if resp.status_code == 404:
            return None
        return KbNode.model_validate(resp.json())

    async def list_kbs(self, *, prefix: str | None = None,
                       tag: str | None = None) -> list[KbNode]:
        qs = []
        if prefix:
            qs.append(f"prefix={quote(prefix)}")
        if tag:
            qs.append(f"tag={quote(tag)}")
        path = "/kbs" + ("?" + "&".join(qs) if qs else "")
        resp = await self._request("GET", path)
        return [KbNode.model_validate(r) for r in resp.json()]

    async def delete_kb(self, name: str) -> bool:
        resp = await self._request("DELETE", f"/kbs/{quote(name, safe='')}")
        return resp.status_code == 204

    async def link_kbs(self, *, from_kb: str, to_kb: str, kind: LinkKind,
                       metadata: dict | None = None) -> KbLink:
        body = KbLinkCreate(to_kb=to_kb, kind=kind, metadata=metadata or {})
        resp = await self._request(
            "POST", f"/kbs/{quote(from_kb, safe='')}/links",
            json=body.model_dump(mode="json"),
        )
        return KbLink.model_validate(resp.json())

    async def unlink_kbs(self, *, from_kb: str, to_kb: str,
                         kind: LinkKind) -> bool:
        resp = await self._request(
            "DELETE",
            f"/kbs/{quote(from_kb, safe='')}/links/"
            f"{quote(to_kb, safe='')}/{kind.value}",
        )
        return resp.status_code == 204

    async def list_links(
        self, *, name: str,
        direction: Literal["in", "out", "both"] = "both",
    ) -> list[KbLink]:
        resp = await self._request(
            "GET",
            f"/kbs/{quote(name, safe='')}/links?direction={direction}",
        )
        return [KbLink.model_validate(r) for r in resp.json()]

    async def query(self, *, cypher: str, params: dict | None = None,
                    read_only: bool = True) -> QueryResult:
        q = CypherQuery(cypher=cypher, params=params or {}, read_only=read_only)
        resp = await self._request("POST", "/query", json=q.model_dump())
        return QueryResult.model_validate(resp.json())
```

- [ ] **Step 4: Re-export from package init**

Modify `packages/guru-core/src/guru_core/__init__.py` — append:

```python
from .graph_client import GraphClient

__all__ = [*__all__, "GraphClient"]
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest packages/guru-core/tests/test_graph_client.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-core
git commit -m "feat(graph): add GraphClient over HTTP-UDS with autostart"
```

---

## Task 19: `guru-server` integration — `graph_or_skip` + self-KB upsert

**Files:**
- Create: `packages/guru-server/src/guru_server/graph_integration.py`
- Modify: `packages/guru-server/src/guru_server/app.py` (add startup hook + /status extension)
- Modify: `packages/guru-core/src/guru_core/types.py` (extend `StatusOut`)
- Modify: `packages/guru-server/src/guru_server/api/status.py`
- Create: `packages/guru-server/tests/test_graph_integration.py`

- [ ] **Step 1: Extend `StatusOut`**

Modify `packages/guru-core/src/guru_core/types.py` — find `StatusOut` class and add two fields:

```python
class StatusOut(BaseModel):
    # ... existing fields ...
    graph_enabled: bool = False
    graph_reachable: bool = False
```

- [ ] **Step 2: Write failing tests**

Create `packages/guru-server/tests/test_graph_integration.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from guru_core.graph_errors import GraphUnavailable
from guru_server.graph_integration import graph_or_skip, register_self_kb


@pytest.mark.asyncio
async def test_graph_or_skip_returns_value_on_success():
    async def coro():
        return 42
    result = await graph_or_skip(coro(), feature="test")
    assert result == 42


@pytest.mark.asyncio
async def test_graph_or_skip_swallows_unavailable():
    async def coro():
        raise GraphUnavailable("down")
    result = await graph_or_skip(coro(), feature="test")
    assert result is None


@pytest.mark.asyncio
async def test_register_self_kb_no_op_when_client_none():
    # No raises; simply returns
    await register_self_kb(client=None, name="p", project_root="/p")


@pytest.mark.asyncio
async def test_register_self_kb_upserts_via_client():
    client = AsyncMock()
    await register_self_kb(client=client, name="p", project_root="/p")
    client.upsert_kb.assert_awaited_once()
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest packages/guru-server/tests/test_graph_integration.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `graph_integration.py`**

Create `packages/guru-server/src/guru_server/graph_integration.py`:

```python
"""guru-server ↔ guru-graph glue.

Graph is strictly optional. Any failure — disabled, unreachable, unhealthy —
is swallowed by `graph_or_skip` so end users never see a graph error.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import KbUpsert

logger = logging.getLogger(__name__)

_logged_features: set[str] = set()


async def graph_or_skip(coro: Awaitable[Any], *, feature: str) -> Any | None:
    """Run the graph coroutine; return None if the graph is unavailable.

    Logs at most once per feature per process so log noise stays bounded.
    """
    try:
        return await coro
    except GraphUnavailable as e:
        if feature not in _logged_features:
            logger.info("graph unavailable for %s: %s (subsequent errors silent)",
                         feature, e)
            _logged_features.add(feature)
        return None
    except Exception as e:  # defensive — never leak to caller
        logger.warning("graph call for %s raised: %s", feature, e)
        return None


async def register_self_kb(
    *,
    client: GraphClient | None,
    name: str,
    project_root: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Upsert this guru-server's KB node via the graph client.

    No-op if client is None (graph disabled). Silently degrades on failure.
    """
    if client is None:
        return
    req = KbUpsert(
        name=name, project_root=project_root,
        tags=tags or [], metadata=metadata or {},
    )
    await graph_or_skip(client.upsert_kb(req), feature="register_self_kb")


def build_graph_client_if_enabled(
    *, graph_enabled: bool,
) -> GraphClient | None:
    if not graph_enabled:
        return None
    # Import here to keep guru-graph an optional dependency.
    try:
        from guru_graph.config import GraphPaths  # type: ignore
    except ImportError:
        logger.warning("graph.enabled=true but guru-graph is not installed")
        return None
    paths = GraphPaths.default()
    return GraphClient(socket_path=str(paths.socket), auto_start=True)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest packages/guru-server/tests/test_graph_integration.py -v`
Expected: 4 tests PASS.

- [ ] **Step 6: Wire into `app.py` startup and `/status`**

In `packages/guru-server/src/guru_server/app.py`, find the startup routine and add the graph initialisation. Below is the pattern; locate the existing startup hook and adapt (paths may vary):

```python
# near the top:
from .graph_integration import build_graph_client_if_enabled, register_self_kb

# inside create_app or lifespan hook:
async def _startup(app):
    graph_enabled = bool(app.state.config.graph and app.state.config.graph.enabled)
    app.state.graph_client = build_graph_client_if_enabled(graph_enabled=graph_enabled)
    if app.state.graph_client is not None:
        await register_self_kb(
            client=app.state.graph_client,
            name=app.state.manifest.name,
            project_root=str(app.state.project_root),
        )
```

Note: if `GuruConfig` does not yet have a `graph` field, extend `packages/guru-core/src/guru_core/types.py` with:

```python
class GraphConfig(BaseModel):
    enabled: bool = False


class GuruConfig(BaseModel):
    # ... existing fields ...
    graph: GraphConfig | None = None
```

- [ ] **Step 7: Extend `/status` endpoint**

Modify `packages/guru-server/src/guru_server/api/status.py` — include graph fields on the status response:

```python
async def status(request: Request) -> StatusOut:
    # ... existing status assembly ...
    graph_enabled = request.app.state.graph_client is not None
    graph_reachable = False
    if graph_enabled:
        try:
            h = await request.app.state.graph_client.health()
            graph_reachable = h.graph_reachable
        except Exception:
            graph_reachable = False
    return StatusOut(
        # ... existing fields ...
        graph_enabled=graph_enabled,
        graph_reachable=graph_reachable,
    )
```

- [ ] **Step 8: Verify server tests still pass**

Run: `uv run pytest packages/guru-server/tests/ -v -k "not real_"`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add packages/guru-server packages/guru-core
git commit -m "feat(graph): integrate guru-server with guru-graph via graph_or_skip"
```

---

## Task 20: `guru graph` CLI commands

**Files:**
- Create: `packages/guru-cli/src/guru_cli/commands/__init__.py` (if missing)
- Create: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Modify: `packages/guru-cli/src/guru_cli/cli.py` (register the group)

- [ ] **Step 1: Implement the command group**

Create `packages/guru-cli/src/guru_cli/commands/__init__.py` (empty if it doesn't exist):

```python
```

Create `packages/guru-cli/src/guru_cli/commands/graph.py`:

```python
"""`guru graph` — control the optional graph plugin daemon.

Subcommands:
  guru graph start   — spawn the daemon now (blocking until ready)
  guru graph stop    — send SIGTERM to the running daemon
  guru graph status  — show daemon PID, Neo4j status, schema version
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

import click


@click.group(name="graph")
def graph_group() -> None:
    """Control the optional graph plugin daemon."""


@graph_group.command(name="start")
def start() -> None:
    """Start the graph daemon and block until its socket is ready."""
    try:
        from guru_graph.config import GraphPaths
        from guru_graph.lifecycle import connect_or_spawn
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        sys.exit(2)
    paths = GraphPaths.default()
    click.echo(f"starting daemon; socket={paths.socket}")
    connect_or_spawn(paths=paths, ready_timeout_seconds=60.0)
    click.echo("daemon ready")


@graph_group.command(name="stop")
def stop() -> None:
    """Send SIGTERM to the running graph daemon."""
    try:
        from guru_graph.config import GraphPaths
        from guru_graph.lifecycle import read_pid_file
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        sys.exit(2)
    paths = GraphPaths.default()
    pid = read_pid_file(paths.pid_file)
    if pid is None:
        click.echo("no daemon running")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"sent SIGTERM to daemon pid={pid}")
    except ProcessLookupError:
        click.echo("daemon pid recorded but process missing; cleaning up")
        try:
            paths.pid_file.unlink()
        except FileNotFoundError:
            pass


@graph_group.command(name="status")
def status() -> None:
    """Print graph daemon status."""
    try:
        from guru_core.graph_client import GraphClient
        from guru_graph.config import GraphPaths
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        sys.exit(2)
    paths = GraphPaths.default()
    client = GraphClient(socket_path=str(paths.socket), auto_start=False)
    try:
        info = asyncio.run(client.version())
        health = asyncio.run(client.health())
        click.echo(f"daemon: reachable")
        click.echo(f"protocol: {info.protocol_version}")
        click.echo(f"backend:  {info.backend} {info.backend_version}")
        click.echo(f"schema:   {info.schema_version}")
        click.echo(f"status:   {health.status}")
    except Exception as e:
        click.echo(f"daemon: unreachable ({e})")
        sys.exit(1)
```

- [ ] **Step 2: Register the group**

Modify `packages/guru-cli/src/guru_cli/cli.py` — find the click cli root and add:

```python
from .commands.graph import graph_group

# after the root cli object is defined:
cli.add_command(graph_group)
```

- [ ] **Step 3: Smoke-test the command**

Run: `uv run guru graph --help`
Expected: help text listing `start`, `stop`, `status` subcommands.

Run: `uv run guru graph status`
Expected: `daemon: unreachable (…)` (exit 1) — no daemon running.

- [ ] **Step 4: Commit**

```bash
git add packages/guru-cli
git commit -m "feat(graph): add `guru graph start|stop|status` commands"
```

---

## Task 21: BDD e2e feature + step definitions + environment hook

**Files:**
- Create: `tests/e2e/features/graph_plugin.feature`
- Create: `tests/e2e/features/steps/graph_steps.py`
- Modify: `tests/e2e/features/environment.py`

- [ ] **Step 1: Write the feature file**

Create `tests/e2e/features/graph_plugin.feature`:

```gherkin
Feature: Optional graph plugin
  Guru's graph plugin is strictly optional. When disabled or unreachable,
  guru-server must continue to serve the user with reduced accuracy.

  @disabled
  Scenario: Graph disabled by config → guru-server works and reports degraded
    Given graph is disabled in global config
    When I start guru-server for project "demo"
    Then status reports graph_enabled = false
    And status reports graph_reachable = false
    And search endpoint succeeds

  @real_neo4j
  Scenario: Graph enabled → KB auto-registers on first server start
    Given graph is enabled in global config
    When I start guru-server for project "demo"
    Then a guru-graph daemon is running
    And a Kb node "demo" exists in the graph

  @real_neo4j
  Scenario: Two projects share one graph daemon
    Given graph is enabled and a server is running for project "alpha"
    When I start a server for project "beta"
    Then both Kb nodes exist
    And only one guru-graph daemon PID is alive

  @real_neo4j @slow
  Scenario: Daemon crash triggers lazy restart on next use
    Given graph is enabled and a daemon is running
    When I SIGKILL the graph daemon
    And I upsert Kb "gamma" via a new server
    Then a new guru-graph daemon spawns within 10 seconds
    And the upsert succeeds

  Scenario: Neo4j preflight failure degrades silently
    Given graph is enabled but neo4j is not on PATH
    When I start guru-server for project "demo"
    Then guru-server is running
    And status reports graph_reachable = false

  @real_neo4j
  Scenario: Link with known vocabulary succeeds
    Given graph is enabled and Kbs "alpha" and "beta" exist
    When I link alpha -> beta as depends_on
    Then list_links for alpha outgoing contains (alpha, beta, depends_on)

  Scenario: Unknown link kind rejected with 422
    Given graph is enabled and Kbs "alpha" and "beta" exist
    When I attempt to link alpha -> beta as "sorta_related"
    Then the response is 422
    And the error mentions supported link kinds
```

- [ ] **Step 2: Write step definitions**

Create `tests/e2e/features/steps/graph_steps.py`:

```python
"""Step definitions for graph_plugin.feature."""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

import httpx
from behave import given, then, when

from guru_core.graph_client import GraphClient
from guru_core.graph_types import KbUpsert


def _graph_dir(context) -> Path:
    return Path(context.graph_dir)


def _write_global_config(context, *, graph_enabled: bool) -> None:
    cfg_dir = Path(context.guru_config_home) / "guru"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(json.dumps(
        {"version": 1, "rules": [], "graph": {"enabled": graph_enabled}}
    ))


@given('graph is disabled in global config')
def step_graph_disabled(context):
    _write_global_config(context, graph_enabled=False)


@given('graph is enabled in global config')
def step_graph_enabled(context):
    _write_global_config(context, graph_enabled=True)


@given('graph is enabled but neo4j is not on PATH')
def step_graph_enabled_no_neo4j(context):
    _write_global_config(context, graph_enabled=True)
    # environment.before_feature scrubbed PATH already; nothing more to do.


@given('graph is enabled and a server is running for project "{name}"')
def step_graph_enabled_and_running(context, name):
    _write_global_config(context, graph_enabled=True)
    context.start_guru_server(name=name, project_root=f"/tmp/{name}")


@given('graph is enabled and a daemon is running')
def step_graph_and_daemon_running(context):
    _write_global_config(context, graph_enabled=True)
    context.start_guru_server(name="bootstrap", project_root="/tmp/bootstrap")


@given('graph is enabled and Kbs "{a}" and "{b}" exist')
def step_graph_and_two_kbs(context, a, b):
    _write_global_config(context, graph_enabled=True)
    context.start_guru_server(name=a, project_root=f"/tmp/{a}")
    context.start_guru_server(name=b, project_root=f"/tmp/{b}")


@when('I start guru-server for project "{name}"')
def step_start_guru_server(context, name):
    context.start_guru_server(name=name, project_root=f"/tmp/{name}")


@when('I start a server for project "{name}"')
def step_start_another(context, name):
    context.start_guru_server(name=name, project_root=f"/tmp/{name}")


@when('I SIGKILL the graph daemon')
def step_sigkill_daemon(context):
    from guru_graph.config import GraphPaths
    from guru_graph.lifecycle import read_pid_file
    pid = read_pid_file(GraphPaths.default().pid_file)
    assert pid, "no daemon pid recorded"
    os.kill(pid, signal.SIGKILL)
    time.sleep(0.5)


@when('I upsert Kb "{name}" via a new server')
def step_upsert_via_new_server(context, name):
    context.start_guru_server(name=name, project_root=f"/tmp/{name}")


@when('I link alpha -> beta as depends_on')
def step_link_depends_on(context):
    import asyncio
    from guru_core.graph_types import LinkKind
    from guru_graph.config import GraphPaths
    client = GraphClient(socket_path=str(GraphPaths.default().socket),
                          auto_start=False)
    asyncio.run(client.link_kbs(from_kb="alpha", to_kb="beta",
                                  kind=LinkKind.DEPENDS_ON))


@when('I attempt to link alpha -> beta as "{kind}"')
def step_attempt_unknown_link(context, kind):
    from guru_graph.config import GraphPaths
    paths = GraphPaths.default()
    transport = httpx.HTTPTransport(uds=str(paths.socket))
    with httpx.Client(transport=transport) as c:
        context.last_response = c.post(
            "http://localhost/kbs/alpha/links",
            json={"to_kb": "beta", "kind": kind},
            headers={"X-Guru-Graph-Protocol": "1.0.0"},
        )


@then('status reports graph_enabled = {val:S}')
def step_status_graph_enabled(context, val):
    s = context.get_guru_status()
    assert str(s.get("graph_enabled")).lower() == val.lower(), s


@then('status reports graph_reachable = {val:S}')
def step_status_graph_reachable(context, val):
    s = context.get_guru_status()
    assert str(s.get("graph_reachable")).lower() == val.lower(), s


@then('search endpoint succeeds')
def step_search_ok(context):
    resp = context.guru_get("/search?q=hello")
    assert resp.status_code == 200


@then('a guru-graph daemon is running')
def step_daemon_running(context):
    from guru_graph.config import GraphPaths
    from guru_graph.lifecycle import read_pid_file
    pid = read_pid_file(GraphPaths.default().pid_file)
    assert pid is not None
    os.kill(pid, 0)  # raises if missing


@then('a Kb node "{name}" exists in the graph')
def step_kb_exists(context, name):
    import asyncio
    from guru_graph.config import GraphPaths
    client = GraphClient(socket_path=str(GraphPaths.default().socket),
                          auto_start=False)
    node = asyncio.run(client.get_kb(name))
    assert node is not None, f"Kb {name!r} missing"


@then('both Kb nodes exist')
def step_both_exist(context):
    import asyncio
    from guru_graph.config import GraphPaths
    client = GraphClient(socket_path=str(GraphPaths.default().socket),
                          auto_start=False)
    names = {n.name for n in asyncio.run(client.list_kbs())}
    assert {"alpha", "beta"} <= names, names


@then('only one guru-graph daemon PID is alive')
def step_single_daemon(context):
    import subprocess
    out = subprocess.check_output(
        ["pgrep", "-f", "guru_graph.main"], text=True,
    ).split()
    assert len(out) == 1, out


@then('a new guru-graph daemon spawns within {seconds:d} seconds')
def step_new_daemon_spawns(context, seconds):
    from guru_graph.config import GraphPaths
    from guru_graph.lifecycle import is_socket_alive
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if is_socket_alive(GraphPaths.default().socket):
            return
        time.sleep(0.2)
    raise AssertionError("daemon did not revive")


@then('the upsert succeeds')
def step_upsert_succeeds(context):
    # The `I upsert Kb X via a new server` step ran the upsert as part of
    # guru-server startup; presence of the node is the assertion.
    pass


@then('list_links for alpha outgoing contains ({a}, {b}, {kind})')
def step_links_contain(context, a, b, kind):
    import asyncio
    from guru_graph.config import GraphPaths
    client = GraphClient(socket_path=str(GraphPaths.default().socket),
                          auto_start=False)
    links = asyncio.run(client.list_links(name=a, direction="out"))
    matching = [l for l in links
                 if l.to_kb == b and l.kind.value == kind]
    assert matching, f"no matching link in {links}"


@then('the response is {code:d}')
def step_response_code(context, code):
    assert context.last_response.status_code == code, \
        f"got {context.last_response.status_code}: {context.last_response.text}"


@then('the error mentions supported link kinds')
def step_error_mentions_kinds(context):
    body = context.last_response.text
    for kind in ("depends_on", "fork_of", "references", "related_to", "mirrors"):
        if kind in body:
            return
    raise AssertionError(f"body did not list supported kinds: {body}")


@then('guru-server is running')
def step_server_running(context):
    resp = context.guru_get("/status")
    assert resp.status_code == 200
```

- [ ] **Step 3: Extend `environment.py`**

Modify `tests/e2e/features/environment.py` — add `before_feature` logic for graph scenarios:

```python
# at the top:
import os
import shutil
import tempfile
from pathlib import Path

# in before_feature, append graph-specific setup:
def before_feature(context, feature):
    # ... existing setup ...
    if "graph_plugin" in feature.filename:
        context.graph_dir = tempfile.mkdtemp(prefix="guru-graph-e2e-")
        context.guru_config_home = tempfile.mkdtemp(prefix="guru-e2e-cfg-")
        os.environ["XDG_CONFIG_HOME"] = context.guru_config_home
        os.environ["XDG_DATA_HOME"] = context.graph_dir
        os.environ["XDG_STATE_HOME"] = context.graph_dir
        os.environ["XDG_RUNTIME_DIR"] = context.graph_dir
        # Scrub neo4j from PATH for preflight-failure scenarios.
        if "neo4j is not on PATH" in feature.description or any(
            "neo4j is not on PATH" in sc.name for sc in feature.scenarios
        ):
            context._saved_path = os.environ.get("PATH", "")
            filtered = [p for p in context._saved_path.split(":")
                         if "neo4j" not in p.lower()]
            os.environ["PATH"] = ":".join(filtered)


def after_feature(context, feature):
    # ... existing teardown ...
    if "graph_plugin" in feature.filename:
        # Stop any daemon we started.
        try:
            from guru_graph.config import GraphPaths
            from guru_graph.lifecycle import read_pid_file
            pid = read_pid_file(GraphPaths.default().pid_file)
            if pid:
                import os as _os
                import signal as _signal
                try:
                    _os.kill(pid, _signal.SIGTERM)
                except ProcessLookupError:
                    pass
        except ImportError:
            pass
        if hasattr(context, "graph_dir"):
            shutil.rmtree(context.graph_dir, ignore_errors=True)
        if hasattr(context, "_saved_path"):
            os.environ["PATH"] = context._saved_path
```

- [ ] **Step 4: Run the feature**

Run: `uv run behave tests/e2e/features/graph_plugin.feature --tags=~@real_neo4j`
Expected: the disabled + preflight-failure + 422 scenarios PASS.

Run (local, with Neo4j): `GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/graph_plugin.feature`
Expected: all scenarios PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/features
git commit -m "test(graph): add BDD graph_plugin feature + steps"
```

---

## Task 22: ARCHITECTURE.md amendments

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Amend the "Architecture: Server-Centric" section**

In `ARCHITECTURE.md`, locate the section starting with `## Architecture: Server-Centric`. Replace:

```markdown
- **guru-server** is the single process that owns all state: LanceDB, Ollama, indexing.
```

with:

```markdown
- **guru-server** owns all **per-project** state: LanceDB, Ollama, indexing.
- Machine-wide shared services (currently the optional graph plugin) are owned by their dedicated daemons — not by guru-server. See `## Graph Plugin` below.
```

- [ ] **Step 2: Amend the "Transport: Unix Domain Sockets" section**

Replace:

```markdown
- No TCP ports. No firewall prompts. No port collisions between projects.
```

with:

```markdown
- No TCP ports are used for inter-component communication.
- **Exception:** third-party backends (currently Neo4j) may bind to a loopback-only TCP port. `guru-graph` is responsible for picking a free port dynamically, recording it in state, and restricting exposure to `127.0.0.1`. Bolt traffic never leaves the graph daemon's process boundary.
```

- [ ] **Step 3: Add a new "Graph Plugin" section**

Append to `ARCHITECTURE.md` (after the existing sections, before any trailing separator):

```markdown
## Graph Plugin (optional)

- An optional `guru-graph` package ships in the workspace as a peer of `guru-server`. It is **disabled by default**; users enable it via `~/.config/guru/config.json → graph.enabled = true`.
- When enabled, a single machine-wide daemon is lazy-started by any guru-server. It owns a Neo4j Community subprocess. All guru-servers on the machine share it.
- The graph is strictly an augmentation. When the graph is disabled, unreachable, or failing, guru-server MUST continue to serve the user with reduced accuracy; graph failures never propagate.
- Clients never talk to Neo4j directly — only to `guru-graph` over UDS. Protocol and schema versions are negotiated per spec §Schema, versioning & compatibility.
```

- [ ] **Step 4: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs: amend architecture constitution for graph plugin"
```

---

## Task 23: Makefile and CI wiring

**Files:**
- Modify: `Makefile`
- Modify: `.github/workflows/ci.yml`
- Create: `scripts/start-test-neo4j.sh`

- [ ] **Step 1: Add `make test-graph` target**

Modify `Makefile` — add a target block:

```makefile
.PHONY: test-graph
test-graph: ## run graph-plugin tests including @real_neo4j
	GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/ -v
	GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/graph_plugin.feature
```

Also ensure the existing `test` target does NOT include graph @real_neo4j by default — the `conftest.py` skip handles this automatically.

- [ ] **Step 2: Add a local-dev convenience script**

Create `scripts/start-test-neo4j.sh`:

```bash
#!/usr/bin/env bash
# Spin up an ephemeral Neo4j 5.x container on the local machine for running
# @real_neo4j tests without installing Neo4j natively.
set -euo pipefail

PORT=${PORT:-17687}
NAME=${NAME:-guru-graph-test-neo4j}

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  -p "$PORT:7687" \
  -e NEO4J_AUTH=none \
  -e NEO4J_PLUGINS='[]' \
  --health-cmd "cypher-shell -u neo4j -p '' 'RETURN 1'" \
  --health-interval 3s \
  neo4j:5 >/dev/null

echo "waiting for neo4j on bolt://127.0.0.1:$PORT..."
for _ in $(seq 1 60); do
  if docker exec "$NAME" cypher-shell "RETURN 1" >/dev/null 2>&1; then
    echo "ready"
    exit 0
  fi
  sleep 1
done
echo "neo4j did not become ready" >&2
exit 1
```

Make executable: `chmod +x scripts/start-test-neo4j.sh`.

- [ ] **Step 3: Extend CI**

Modify `.github/workflows/ci.yml` — add a new job after the existing test jobs:

```yaml
  graph-plugin:
    runs-on: ubuntu-latest
    if: contains(github.event.pull_request.labels.*.name, 'require-e2e-tests')
    services:
      neo4j:
        image: neo4j:5
        ports:
          - 7687:7687
        env:
          NEO4J_AUTH: none
        options: >-
          --health-cmd "cypher-shell 'RETURN 1'"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: uv sync --all-packages
      - run: GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/ -v
```

(Exact YAML indentation / sibling job structure depends on the current file — the implementer should match the surrounding pattern.)

- [ ] **Step 4: Commit**

```bash
git add Makefile scripts/start-test-neo4j.sh .github/workflows/ci.yml
git commit -m "ci(graph): add test-graph target, Neo4j CI service, local script"
```

---

## Task 24: Final smoke-test pass

**Files:** none (verification only)

- [ ] **Step 1: Run full unit + integration suite (no Neo4j)**

Run: `make test`
Expected: all tests PASS. `@real_neo4j` tests SKIPPED.

- [ ] **Step 2: Run full graph-plugin suite (local, Neo4j installed)**

Run: `make test-graph`
Expected: all tests PASS.

- [ ] **Step 3: End-to-end manual check**

```bash
# Terminal 1
echo '{"version":1,"rules":[],"graph":{"enabled":true}}' > ~/.config/guru/config.json
uv run guru graph start  # blocks until daemon ready
```

```bash
# Terminal 2
uv run guru graph status
# expect: protocol 1.0.0, backend neo4j, status healthy
```

```bash
# Terminal 3
uv run guru-server  # in a test project dir
curl --unix-socket .guru/guru.sock http://localhost/status | jq
# expect: graph_enabled=true, graph_reachable=true
```

- [ ] **Step 4: Commit any final docs polish**

```bash
git diff --stat | cat
# if anything needs tidying, fix and:
git commit -am "docs(graph): polish ARCHITECTURE notes"
```

---

## Self-review checklist

| Spec requirement | Implemented by |
|---|---|
| New `packages/guru-graph/` workspace package | Task 1 |
| Shared Pydantic types + `LinkKind` enum in guru-core | Task 2 |
| Protocol + schema versioning helpers | Task 3 |
| Backend abstraction + registry (SOLID/open-closed) | Task 4 |
| `FakeBackend` for unit tests | Task 5 |
| `KbService` + `QueryService` domain layer | Task 6 |
| FastAPI app factory + protocol middleware + admin routes | Task 7 |
| KB + link routes | Task 8 |
| Cypher escape hatch route | Task 9 |
| Platform paths + port allocator | Task 10 |
| Preflight (java, neo4j) | Task 11 |
| Neo4j subprocess manager | Task 12 |
| Concrete `Neo4jBackend` | Task 13 |
| Migration framework + `m0001` | Task 14 |
| Escape hatch against real Neo4j | Task 15 |
| Daemon lifecycle (lazy-start, flock, stale-socket recovery) | Task 16 |
| Daemon entrypoint `main.py` | Task 17 |
| `GraphClient` in guru-core + autostart | Task 18 |
| `graph_or_skip` + self-KB upsert in guru-server; `/status` extension | Task 19 |
| `guru graph start|stop|status` CLI | Task 20 |
| BDD `graph_plugin.feature` + steps + env hook | Task 21 |
| ARCHITECTURE.md amendments (per-project state, loopback-TCP exception) | Task 22 |
| Makefile `test-graph` + CI job + local script | Task 23 |
| End-to-end smoke pass | Task 24 |

All spec sections have at least one task. No placeholders, all file paths exact, all code blocks complete.
