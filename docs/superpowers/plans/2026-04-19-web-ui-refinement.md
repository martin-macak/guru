# Web UI Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the guru workbench web UI around three surfaces (Documents, Graph, Status), remove the "artifact" vocabulary and hallucinated mocks, introduce a LanceDB ↔ graph sync invariant with server-side enforcement, and fix graph behavior (always-on federation/KB root, incremental expand, path-to-root overlay, Cypher-result projection).

**Architecture:** Server-side: add `SyncService` in `guru-server` that mirrors LanceDB's document set into the graph DB whenever graph is enabled, plus four new endpoints (`POST /documents/search`, `GET /graph/roots`, `GET /sync/status`, `POST /sync/reconcile`); filter existing graph neighbor responses to document-kind nodes; standardise the Cypher query response shape. Web-side: replace the current four-surface shell (investigate/graph/query/operate) with three surfaces (documents/graph/status), delete all hardcoded mock data and the "artifact" word from strings/components, add a closeable right metadata pane persisted in `localStorage`, and reshape the graph canvas around a synthetic client-only federation root + real KB nodes with incremental expansion, dashed path-to-root overlay, and Cypher projection.

**Tech Stack:** FastAPI + pydantic (server), React 18 + React Router v7 + ReactFlow 11 + TailwindCSS + Vite + Vitest (web), behave + Playwright (e2e), pytest (unit).

**Spec:** [`docs/superpowers/specs/2026-04-19-web-ui-refinement-design.md`](../specs/2026-04-19-web-ui-refinement-design.md).

---

## Phase 0 — Shared types and test infrastructure

### Task 0.1: Add shared types to guru-core

**Files:**
- Modify: `packages/guru-core/src/guru_core/graph_types.py`
- Test: `packages/guru-core/tests/test_sync_types.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# packages/guru-core/tests/test_sync_types.py
from datetime import datetime, UTC

import pytest
from pydantic import ValidationError

from guru_core.graph_types import (
    DocumentSearchHit,
    FederationRootNode,
    GraphRootsPayload,
    KbNode,
    SyncStatus,
)


def test_sync_status_defaults():
    status = SyncStatus(
        lancedb_count=10,
        graph_count=10,
        drift=0,
        last_reconciled_at=None,
        graph_enabled=True,
    )
    assert status.drift == 0
    assert status.graph_enabled is True


def test_sync_status_rejects_negative_counts():
    with pytest.raises(ValidationError):
        SyncStatus(
            lancedb_count=-1,
            graph_count=0,
            drift=0,
            last_reconciled_at=None,
            graph_enabled=True,
        )


def test_document_search_hit_shape():
    hit = DocumentSearchHit(path="README.md", title="Readme", excerpt="...", score=0.87)
    assert hit.score == pytest.approx(0.87)


def test_graph_roots_payload_holds_federation_and_kbs():
    now = datetime.now(tz=UTC)
    kb = KbNode(
        name="local",
        project_root="/tmp/x",
        created_at=now,
        updated_at=now,
        last_seen_at=None,
        tags=[],
        metadata={},
    )
    payload = GraphRootsPayload(
        federation_root=FederationRootNode(id="federation", label="Federation"),
        kbs=[kb],
    )
    assert payload.federation_root.id == "federation"
    assert payload.kbs[0].name == "local"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/guru-core/tests/test_sync_types.py -v`
Expected: FAIL — `ImportError` for the new names.

- [ ] **Step 3: Implement the new types**

Append to `packages/guru-core/src/guru_core/graph_types.py`:

```python
class SyncStatus(BaseModel):
    """LanceDB ↔ graph sync health.

    `drift` is the count of documents present in one store but not the
    other. When graph is disabled, drift is reported as the count of
    LanceDB documents (nothing to mirror against).
    """

    model_config = ConfigDict(frozen=True)

    lancedb_count: int = Field(ge=0)
    graph_count: int = Field(ge=0)
    drift: int = Field(ge=0)
    last_reconciled_at: datetime | None
    graph_enabled: bool


class DocumentSearchHit(BaseModel):
    """A single similarity-search result surfaced to the web UI."""

    model_config = ConfigDict(frozen=True)

    path: str
    title: str
    excerpt: str
    score: float


class FederationRootNode(BaseModel):
    """Synthetic UI-only orientation root for the graph canvas.

    The server sends this down in `GET /graph/roots` so clients share one
    shape. It is NEVER stored in the graph and is excluded from
    `POST /graph/query` results.
    """

    model_config = ConfigDict(frozen=True)

    id: Literal["federation"] = "federation"
    label: str = "Federation"


class GraphRootsPayload(BaseModel):
    """Initial canvas payload — federation root + all KB nodes."""

    model_config = ConfigDict(frozen=True)

    federation_root: FederationRootNode
    kbs: list[KbNode]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/guru-core/tests/test_sync_types.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-core/src/guru_core/graph_types.py packages/guru-core/tests/test_sync_types.py
git commit -m "feat(core): add SyncStatus, DocumentSearchHit, GraphRootsPayload types"
```

---

### Task 0.2: Add Playwright dev dependency

**Files:**
- Modify: `pyproject.toml` (root, dev-dependencies group)
- Modify: `tests/e2e/features/environment.py` (wire optional Playwright browser)

- [ ] **Step 1: Add Playwright to workspace dev deps**

Append `playwright` to the `[dependency-groups].dev` list in the root `pyproject.toml`. Example:

```toml
[dependency-groups]
dev = [
    # ...existing...
    "playwright>=1.47,<2.0",
]
```

Then run:

```bash
uv sync --all-packages
uv run playwright install chromium
```

Expected: Chromium downloaded, no errors.

- [ ] **Step 2: Add a Playwright fixture to the behave environment**

Edit `tests/e2e/features/environment.py`. Add a scenario-scoped fixture that starts a browser only when the feature is tagged `@web`:

```python
# top of file imports
from playwright.sync_api import sync_playwright


def before_scenario(context, scenario):
    # ...existing behavior...
    if "web" in scenario.effective_tags:
        context._playwright = sync_playwright().start()
        context.browser = context._playwright.chromium.launch(headless=True)
        context.page = context.browser.new_page()


def after_scenario(context, scenario):
    # ...existing behavior...
    if getattr(context, "page", None) is not None:
        context.page.close()
        context.browser.close()
        context._playwright.stop()
        context.page = None
```

Only add the two branches; keep the existing hook bodies intact.

- [ ] **Step 3: Smoke-check with a single web scenario**

Create `tests/e2e/features/web_smoke.feature`:

```gherkin
@web
Feature: Web smoke

  Scenario: Workbench serves the boot payload
    Given a guru server is running
    When I open the workbench in a browser
    Then I see the "Documents" menu item
```

Add the missing steps in `tests/e2e/features/steps/web_steps.py` (create):

```python
from behave import given, then, when


@when('I open the workbench in a browser')
def step_open_workbench(context):
    context.page.goto(f"{context.server_url}/")
    context.page.wait_for_load_state("networkidle")


@then('I see the "{label}" menu item')
def step_menu_item(context, label):
    assert context.page.get_by_role("link", name=label).is_visible()
```

- [ ] **Step 4: Run the smoke feature**

Run: `uv run behave tests/e2e/features/web_smoke.feature -t @web`
Expected: 1 scenario, 1 passing (will fail at the `Documents` assertion until Phase 3 — leave the feature file in place but xfail-tag it).

Re-tag the scenario with `@xfail_until_phase_3` so CI ignores it for now:

```gherkin
@web @xfail_until_phase_3
Feature: Web smoke
  # ...
```

Add `@xfail_until_phase_3` handling in `environment.py` (skip the scenario if tagged). Minimum:

```python
def before_scenario(context, scenario):
    if "xfail_until_phase_3" in scenario.effective_tags:
        scenario.skip("Waiting for phase 3")
        return
    # ...rest...
```

Run again: `uv run behave tests/e2e/features/web_smoke.feature`
Expected: 1 scenario, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/e2e/features/environment.py tests/e2e/features/web_smoke.feature tests/e2e/features/steps/web_steps.py
git commit -m "chore(e2e): add Playwright dev dep and web scenario scaffold"
```

---

## Phase 1 — Sync invariant (server-only)

### Task 1.1: Define the `SyncService` API and per-KB lock

**Files:**
- Create: `packages/guru-server/src/guru_server/sync.py`
- Test: `packages/guru-server/tests/test_sync_service.py` (create)

- [ ] **Step 1: Write failing tests**

```python
# packages/guru-server/tests/test_sync_service.py
from __future__ import annotations

import threading
import time

import pytest

from guru_server.sync import SyncService


class FakeLanceStore:
    def __init__(self, ids: list[str]):
        self._ids = list(ids)

    def list_document_ids(self) -> list[str]:
        return list(self._ids)

    def get_document(self, doc_id: str) -> dict:
        return {"id": doc_id, "title": doc_id, "path": doc_id}


class FakeGraphBackend:
    def __init__(self, kb: str, ids: list[str] | None = None, enabled: bool = True):
        self.kb = kb
        self._ids = set(ids or [])
        self.enabled = enabled
        self.upserts: list[str] = []
        self.deletes: list[str] = []

    def is_enabled(self) -> bool:
        return self.enabled

    def list_document_node_ids(self, kb: str) -> list[str]:
        assert kb == self.kb
        return list(self._ids)

    def upsert_document_node(self, kb: str, document: dict) -> None:
        assert kb == self.kb
        self._ids.add(document["id"])
        self.upserts.append(document["id"])

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        assert kb == self.kb
        self._ids.discard(doc_id)
        self.deletes.append(doc_id)


def test_reconcile_heals_missing_and_stale_nodes():
    lance = FakeLanceStore(ids=["a", "b", "c"])
    graph = FakeGraphBackend(kb="local", ids=["b", "c", "d"])  # missing a, stale d
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = svc.reconcile()

    assert graph.upserts == ["a"]
    assert graph.deletes == ["d"]
    assert status.lancedb_count == 3
    assert status.graph_count == 3
    assert status.drift == 0
    assert status.graph_enabled is True


def test_status_without_reconcile_reports_drift():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local", ids=["b"])
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = svc.status()
    assert status.lancedb_count == 2
    assert status.graph_count == 1
    assert status.drift == 1


def test_status_when_graph_disabled_sets_flag_and_drift_to_lancedb_count():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local", ids=[], enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)

    status = svc.status()
    assert status.graph_enabled is False
    assert status.lancedb_count == 2
    assert status.graph_count == 0
    assert status.drift == 2


def test_reconcile_raises_when_graph_disabled():
    lance = FakeLanceStore(ids=["a"])
    graph = FakeGraphBackend(kb="local", enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)

    with pytest.raises(RuntimeError, match="graph is disabled"):
        svc.reconcile()


def test_reconcile_is_serialised_per_kb():
    lance = FakeLanceStore(ids=["a", "b"])
    graph = FakeGraphBackend(kb="local")
    svc = SyncService(kb="local", lance=lance, graph=graph)

    entered = threading.Event()
    release = threading.Event()
    original_upsert = graph.upsert_document_node

    def slow_upsert(kb, document):
        entered.set()
        release.wait(timeout=2)
        original_upsert(kb, document)

    graph.upsert_document_node = slow_upsert

    t = threading.Thread(target=svc.reconcile)
    t.start()
    assert entered.wait(timeout=2)

    start = time.monotonic()
    blocker = threading.Thread(target=svc.reconcile)
    blocker.start()
    time.sleep(0.1)
    assert blocker.is_alive(), "second reconcile should block on the lock"

    release.set()
    t.join(timeout=2)
    blocker.join(timeout=2)
    assert not blocker.is_alive()
    assert time.monotonic() - start < 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_sync_service.py -v`
Expected: all ERRORs — `SyncService` does not exist yet.

- [ ] **Step 3: Implement `SyncService`**

```python
# packages/guru-server/src/guru_server/sync.py
"""LanceDB ↔ graph sync invariant enforcement.

`SyncService` guarantees that for every document in LanceDB a corresponding
document-kind graph node exists under its local KB whenever the graph daemon
is enabled. The service is intentionally narrow: it knows nothing about HTTP,
FastAPI, or ingestion pipelines; those wire it up.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Protocol

from guru_core.graph_types import SyncStatus

logger = logging.getLogger(__name__)


class LanceStore(Protocol):
    def list_document_ids(self) -> list[str]: ...
    def get_document(self, doc_id: str) -> dict: ...


class GraphBackend(Protocol):
    def is_enabled(self) -> bool: ...
    def list_document_node_ids(self, kb: str) -> list[str]: ...
    def upsert_document_node(self, kb: str, document: dict) -> None: ...
    def delete_document_node(self, kb: str, doc_id: str) -> None: ...


class SyncService:
    def __init__(self, *, kb: str, lance: LanceStore, graph: GraphBackend) -> None:
        self._kb = kb
        self._lance = lance
        self._graph = graph
        self._lock = threading.Lock()
        self._last_reconciled_at: datetime | None = None

    def status(self) -> SyncStatus:
        lance_ids = set(self._lance.list_document_ids())
        lancedb_count = len(lance_ids)

        if not self._graph.is_enabled():
            return SyncStatus(
                lancedb_count=lancedb_count,
                graph_count=0,
                drift=lancedb_count,
                last_reconciled_at=self._last_reconciled_at,
                graph_enabled=False,
            )

        graph_ids = set(self._graph.list_document_node_ids(self._kb))
        drift = len(lance_ids.symmetric_difference(graph_ids))
        return SyncStatus(
            lancedb_count=lancedb_count,
            graph_count=len(graph_ids),
            drift=drift,
            last_reconciled_at=self._last_reconciled_at,
            graph_enabled=True,
        )

    def reconcile(self) -> SyncStatus:
        if not self._graph.is_enabled():
            raise RuntimeError("cannot reconcile: graph is disabled")

        with self._lock:
            lance_ids = set(self._lance.list_document_ids())
            graph_ids = set(self._graph.list_document_node_ids(self._kb))

            missing = sorted(lance_ids - graph_ids)
            stale = sorted(graph_ids - lance_ids)

            for doc_id in missing:
                doc = self._lance.get_document(doc_id)
                self._graph.upsert_document_node(self._kb, doc)

            for doc_id in stale:
                self._graph.delete_document_node(self._kb, doc_id)

            self._last_reconciled_at = datetime.now(tz=UTC)
            logger.info(
                "sync.reconcile kb=%s upserts=%d deletes=%d",
                self._kb,
                len(missing),
                len(stale),
            )
            return SyncStatus(
                lancedb_count=len(lance_ids),
                graph_count=len(lance_ids),
                drift=0,
                last_reconciled_at=self._last_reconciled_at,
                graph_enabled=True,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_sync_service.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/sync.py packages/guru-server/tests/test_sync_service.py
git commit -m "feat(server): add SyncService for LanceDB↔graph invariant"
```

---

### Task 1.2: Wire a real `LanceStore` adapter

**Files:**
- Modify: `packages/guru-server/src/guru_server/sync.py`
- Test: `packages/guru-server/tests/test_sync_lance_adapter.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_sync_lance_adapter.py
from __future__ import annotations

from guru_server.sync import LanceDocumentAdapter


class FakeStore:
    def __init__(self, rows):
        self._rows = rows

    def list_documents(self):
        return [{"path": r["path"], "title": r["title"]} for r in self._rows]

    def get_document(self, path):
        for r in self._rows:
            if r["path"] == path:
                return r
        return None


def test_adapter_enumerates_ids_from_store():
    store = FakeStore([{"path": "a.md", "title": "A"}, {"path": "b.md", "title": "B"}])
    adapter = LanceDocumentAdapter(store=store)
    assert adapter.list_document_ids() == ["a.md", "b.md"]


def test_adapter_returns_document_payload():
    store = FakeStore([{"path": "a.md", "title": "A"}])
    adapter = LanceDocumentAdapter(store=store)
    assert adapter.get_document("a.md") == {"id": "a.md", "title": "A", "path": "a.md"}
```

- [ ] **Step 2: Run test — should fail**

Run: `uv run pytest packages/guru-server/tests/test_sync_lance_adapter.py -v`
Expected: FAIL, `LanceDocumentAdapter` does not exist.

- [ ] **Step 3: Implement adapter**

Append to `packages/guru-server/src/guru_server/sync.py`:

```python
class LanceDocumentAdapter:
    """Adapts the existing guru-server document store to the LanceStore protocol.

    The store-side API exposes a richer row shape; this adapter collapses it
    to the `(id, title, path)` triple that `SyncService` needs to mirror into
    the graph.
    """

    def __init__(self, *, store) -> None:  # noqa: ANN001 — store has a project-local type
        self._store = store

    def list_document_ids(self) -> list[str]:
        return [row["path"] for row in self._store.list_documents()]

    def get_document(self, doc_id: str) -> dict:
        row = self._store.get_document(doc_id)
        if row is None:
            raise KeyError(doc_id)
        return {"id": row["path"], "title": row["title"], "path": row["path"]}
```

- [ ] **Step 4: Run test again**

Run: `uv run pytest packages/guru-server/tests/test_sync_lance_adapter.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/sync.py packages/guru-server/tests/test_sync_lance_adapter.py
git commit -m "feat(server): add LanceDocumentAdapter for SyncService"
```

---

### Task 1.3: Wire a real `GraphBackend` adapter

**Files:**
- Modify: `packages/guru-server/src/guru_server/sync.py`
- Test: `packages/guru-server/tests/test_sync_graph_adapter.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_sync_graph_adapter.py
from __future__ import annotations

from guru_server.sync import GraphSyncAdapter


class FakeGraphClient:
    def __init__(self, enabled=True, node_ids=None):
        self.enabled = enabled
        self._nodes = dict((n, {"id": n, "kind": "document"}) for n in node_ids or [])
        self.upserts = []
        self.deletes = []

    def is_available(self):
        return self.enabled

    def list_document_nodes(self, kb):
        return [{"id": n, "kind": "document"} for n in self._nodes]

    def upsert_document_node(self, kb, document):
        self._nodes[document["id"]] = {"id": document["id"], "kind": "document"}
        self.upserts.append((kb, document["id"]))

    def delete_document_node(self, kb, doc_id):
        self._nodes.pop(doc_id, None)
        self.deletes.append((kb, doc_id))


def test_adapter_passes_through_enable_flag():
    client = FakeGraphClient(enabled=False)
    adapter = GraphSyncAdapter(client=client)
    assert adapter.is_enabled() is False


def test_adapter_lists_document_node_ids():
    client = FakeGraphClient(enabled=True, node_ids=["a.md", "b.md"])
    adapter = GraphSyncAdapter(client=client)
    assert sorted(adapter.list_document_node_ids("local")) == ["a.md", "b.md"]


def test_adapter_upsert_and_delete_forward_to_client():
    client = FakeGraphClient(enabled=True)
    adapter = GraphSyncAdapter(client=client)
    adapter.upsert_document_node("local", {"id": "a.md", "title": "A", "path": "a.md"})
    adapter.delete_document_node("local", "a.md")
    assert client.upserts == [("local", "a.md")]
    assert client.deletes == [("local", "a.md")]
```

- [ ] **Step 2: Run test — should fail**

Run: `uv run pytest packages/guru-server/tests/test_sync_graph_adapter.py -v`
Expected: FAIL, `GraphSyncAdapter` does not exist.

- [ ] **Step 3: Implement adapter**

Append to `packages/guru-server/src/guru_server/sync.py`:

```python
class GraphSyncAdapter:
    """Adapts `GraphClient` (from guru-core) to the GraphBackend protocol.

    Only document-kind nodes are visible through this adapter; parser-
    extracted code nodes belong to other subsystems (MCP/CLI) and must not
    be touched by SyncService.
    """

    def __init__(self, *, client) -> None:  # noqa: ANN001 — client typed in caller
        self._client = client

    def is_enabled(self) -> bool:
        return bool(self._client.is_available())

    def list_document_node_ids(self, kb: str) -> list[str]:
        return [node["id"] for node in self._client.list_document_nodes(kb)]

    def upsert_document_node(self, kb: str, document: dict) -> None:
        self._client.upsert_document_node(kb, document)

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        self._client.delete_document_node(kb, doc_id)
```

- [ ] **Step 4: Run test again**

Run: `uv run pytest packages/guru-server/tests/test_sync_graph_adapter.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/sync.py packages/guru-server/tests/test_sync_graph_adapter.py
git commit -m "feat(server): add GraphSyncAdapter for SyncService"
```

---

### Task 1.4: Extend `GraphClient` with document-node CRUD

**Files:**
- Modify: `packages/guru-core/src/guru_core/client.py`
- Modify: `packages/guru-graph/src/guru_graph/routes/kbs.py` (or wherever the graph daemon exposes artifact/document CRUD) — add `/graph/documents/{kb}` handlers
- Test: `packages/guru-core/tests/test_graph_client_documents.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-core/tests/test_graph_client_documents.py
from __future__ import annotations

import httpx
import pytest

from guru_core.client import GraphClient


@pytest.fixture
def mock_graph(respx_mock):
    respx_mock.get("http://graph/graph/documents/local").mock(
        return_value=httpx.Response(
            200,
            json={"nodes": [{"id": "a.md", "kind": "document"}, {"id": "b.md", "kind": "document"}]},
        )
    )
    respx_mock.post("http://graph/graph/documents/local").mock(return_value=httpx.Response(204))
    respx_mock.delete("http://graph/graph/documents/local/a.md").mock(return_value=httpx.Response(204))
    return respx_mock


def test_list_document_nodes(mock_graph):
    client = GraphClient(base_url="http://graph")
    nodes = client.list_document_nodes("local")
    assert [n["id"] for n in nodes] == ["a.md", "b.md"]


def test_upsert_document_node(mock_graph):
    client = GraphClient(base_url="http://graph")
    client.upsert_document_node("local", {"id": "a.md", "title": "A", "path": "a.md"})


def test_delete_document_node(mock_graph):
    client = GraphClient(base_url="http://graph")
    client.delete_document_node("local", "a.md")
```

If `respx` isn't already a dev dep, add it to the root `pyproject.toml` `[dependency-groups].dev`.

- [ ] **Step 2: Run test — should fail**

Run: `uv run pytest packages/guru-core/tests/test_graph_client_documents.py -v`
Expected: FAIL, methods don't exist on `GraphClient`.

- [ ] **Step 3: Add methods to `GraphClient`**

In `packages/guru-core/src/guru_core/client.py`, add to the `GraphClient` class:

```python
    def list_document_nodes(self, kb: str) -> list[dict]:
        resp = self._http.get(f"/graph/documents/{kb}")
        resp.raise_for_status()
        return resp.json().get("nodes", [])

    def upsert_document_node(self, kb: str, document: dict) -> None:
        resp = self._http.post(f"/graph/documents/{kb}", json=document)
        resp.raise_for_status()

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        resp = self._http.delete(f"/graph/documents/{kb}/{doc_id}")
        resp.raise_for_status()
```

- [ ] **Step 4: Add the daemon-side routes**

In `packages/guru-graph/src/guru_graph/routes/`, create `documents.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

router = APIRouter()


class DocumentUpsert(BaseModel):
    id: str
    title: str
    path: str
    metadata: dict = Field(default_factory=dict)


@router.get("/graph/documents/{kb}")
def list_document_nodes(kb: str, request: Request):
    backend = request.app.state.backend
    rows = backend.list_document_nodes(kb)
    return {"nodes": rows}


@router.post("/graph/documents/{kb}", status_code=status.HTTP_204_NO_CONTENT)
def upsert_document_node(kb: str, body: DocumentUpsert, request: Request):
    backend = request.app.state.backend
    backend.upsert_document_node(kb=kb, document=body.model_dump())


@router.delete("/graph/documents/{kb}/{doc_id:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_node(kb: str, doc_id: str, request: Request):
    backend = request.app.state.backend
    backend.delete_document_node(kb=kb, doc_id=doc_id)
```

Register it in the graph app startup (look for `app.include_router(kbs.router)` and add `documents.router` alongside).

Add matching `list_document_nodes`, `upsert_document_node`, `delete_document_node` methods to:
- `packages/guru-graph/src/guru_graph/backend/base.py` (abstract)
- `packages/guru-graph/src/guru_graph/backend/neo4j_backend.py` (Cypher impl — `MERGE`/`DETACH DELETE` on `:Document` labels)
- `packages/guru-graph/src/guru_graph/testing/fake_backend.py` (in-memory)

Backend method signatures:

```python
def list_document_nodes(self, kb: str) -> list[dict]: ...
def upsert_document_node(self, kb: str, document: dict) -> None: ...
def delete_document_node(self, kb: str, doc_id: str) -> None: ...
```

Cypher for the Neo4j backend's upsert:

```cypher
MATCH (k:Kb {name: $kb})
MERGE (d:Document {id: $id, kb: $kb})
  ON CREATE SET d.created_at = timestamp()
SET d.title = $title, d.path = $path, d.updated_at = timestamp()
MERGE (k)-[:CONTAINS]->(d)
```

Cypher for list:

```cypher
MATCH (d:Document {kb: $kb}) RETURN d.id AS id, d.title AS title, d.path AS path
```

Cypher for delete:

```cypher
MATCH (d:Document {id: $id, kb: $kb}) DETACH DELETE d
```

In-memory (`fake_backend.py`) should mirror the semantics with a dict keyed by `(kb, id)`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest packages/guru-core/tests/test_graph_client_documents.py -v
uv run pytest packages/guru-graph/tests/ -v
```

Expected: all PASS. (You will need to add backend tests in `packages/guru-graph/tests/test_fake_backend.py` for the three new methods; add them inline.)

- [ ] **Step 6: Commit**

```bash
git add packages/guru-core/src/guru_core/client.py packages/guru-core/tests/test_graph_client_documents.py packages/guru-graph/src/guru_graph/ packages/guru-graph/tests/
git commit -m "feat(graph): add Document node CRUD to daemon and GraphClient"
```

---

### Task 1.5: Wire `SyncService` into server startup

**Files:**
- Modify: `packages/guru-server/src/guru_server/startup.py`
- Modify: `packages/guru-server/src/guru_server/app.py`
- Test: `packages/guru-server/tests/test_startup_sync.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_startup_sync.py
from __future__ import annotations

from unittest.mock import MagicMock

from guru_server.startup import run_startup_reconcile


def test_startup_reconcile_runs_when_graph_enabled():
    sync = MagicMock()
    sync.status.return_value = MagicMock(graph_enabled=True, drift=2)
    run_startup_reconcile(sync)
    sync.reconcile.assert_called_once()


def test_startup_reconcile_skips_when_graph_disabled():
    sync = MagicMock()
    sync.status.return_value = MagicMock(graph_enabled=False, drift=5)
    run_startup_reconcile(sync)
    sync.reconcile.assert_not_called()


def test_startup_reconcile_skips_when_no_drift():
    sync = MagicMock()
    sync.status.return_value = MagicMock(graph_enabled=True, drift=0)
    run_startup_reconcile(sync)
    sync.reconcile.assert_not_called()
```

- [ ] **Step 2: Run test — should fail**

Run: `uv run pytest packages/guru-server/tests/test_startup_sync.py -v`
Expected: FAIL, `run_startup_reconcile` does not exist.

- [ ] **Step 3: Implement**

Append to `packages/guru-server/src/guru_server/startup.py`:

```python
import logging

from guru_server.sync import SyncService

_logger = logging.getLogger(__name__)


def run_startup_reconcile(sync: SyncService) -> None:
    """Run a best-effort reconcile on server boot when there's drift."""
    status = sync.status()
    if not status.graph_enabled:
        _logger.info("startup.reconcile skipped: graph disabled")
        return
    if status.drift == 0:
        _logger.info("startup.reconcile skipped: no drift (lancedb=%d graph=%d)",
                     status.lancedb_count, status.graph_count)
        return
    _logger.warning("startup.reconcile begin: drift=%d", status.drift)
    sync.reconcile()
    _logger.info("startup.reconcile complete")
```

- [ ] **Step 4: Run test to verify pass**

Run: `uv run pytest packages/guru-server/tests/test_startup_sync.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Instantiate `SyncService` in `app.py`**

In `packages/guru-server/src/guru_server/app.py`, locate the FastAPI startup/init block that wires `app.state.store` and `app.state.graph_client`. Add:

```python
from guru_server.sync import SyncService, LanceDocumentAdapter, GraphSyncAdapter
from guru_server.startup import run_startup_reconcile

# ...after store and graph_client are attached to app.state...
app.state.sync = SyncService(
    kb=config.kb_name,
    lance=LanceDocumentAdapter(store=app.state.store),
    graph=GraphSyncAdapter(client=app.state.graph_client),
)

@app.on_event("startup")
async def _startup_reconcile():
    run_startup_reconcile(app.state.sync)
```

Use the existing `kb_name` from `config.py` (it already carries project name). If no existing attribute, add `kb_name` to the config model and source it from the `guru.json` project root name (fallback to `"local"`).

- [ ] **Step 6: Run full server tests**

Run: `uv run pytest packages/guru-server/tests/ -v`
Expected: existing tests pass; new test passes.

- [ ] **Step 7: Commit**

```bash
git add packages/guru-server/src/guru_server/startup.py packages/guru-server/src/guru_server/app.py packages/guru-server/tests/test_startup_sync.py
git commit -m "feat(server): wire SyncService into startup reconcile"
```

---

### Task 1.6: Hook the indexer to upsert the graph node on ingest

**Files:**
- Modify: `packages/guru-server/src/guru_server/indexer.py`
- Modify: `packages/guru-server/src/guru_server/storage.py` (if ingest finalisation lives there)
- Test: `packages/guru-server/tests/test_indexer_sync.py` (create)

- [ ] **Step 1: Locate the ingest-complete hook**

Run: `grep -n "def ingest\|async def ingest\|add_document\|upsert_document" packages/guru-server/src/guru_server/indexer.py packages/guru-server/src/guru_server/storage.py`

Identify the function that finalises a successful LanceDB insert. That is the hook site.

- [ ] **Step 2: Write failing test**

```python
# packages/guru-server/tests/test_indexer_sync.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from guru_server.indexer import finalize_indexed_document


def test_finalize_upserts_graph_node_when_enabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = True
    document = {"id": "a.md", "title": "A", "path": "a.md"}
    finalize_indexed_document(sync, document)
    sync.upsert_one.assert_called_once_with(document)


def test_finalize_noop_when_disabled():
    sync = MagicMock()
    sync.graph_enabled.return_value = False
    finalize_indexed_document(sync, {"id": "a.md", "title": "A", "path": "a.md"})
    sync.upsert_one.assert_not_called()
```

- [ ] **Step 3: Run test — should fail**

Run: `uv run pytest packages/guru-server/tests/test_indexer_sync.py -v`
Expected: FAIL (missing `finalize_indexed_document`, missing `sync.upsert_one`).

- [ ] **Step 4: Add `upsert_one` / `delete_one` / `graph_enabled` to `SyncService`**

Append to `packages/guru-server/src/guru_server/sync.py`, class `SyncService`:

```python
    def graph_enabled(self) -> bool:
        return self._graph.is_enabled()

    def upsert_one(self, document: dict) -> None:
        if not self._graph.is_enabled():
            return
        with self._lock:
            self._graph.upsert_document_node(self._kb, document)

    def delete_one(self, doc_id: str) -> None:
        if not self._graph.is_enabled():
            return
        with self._lock:
            self._graph.delete_document_node(self._kb, doc_id)
```

Add tests for these three methods in `test_sync_service.py`:

```python
def test_upsert_one_forwards_when_enabled():
    lance = FakeLanceStore(ids=[])
    graph = FakeGraphBackend(kb="local")
    svc = SyncService(kb="local", lance=lance, graph=graph)
    svc.upsert_one({"id": "a.md", "title": "A", "path": "a.md"})
    assert graph.upserts == ["a.md"]


def test_upsert_one_noop_when_disabled():
    lance = FakeLanceStore(ids=[])
    graph = FakeGraphBackend(kb="local", enabled=False)
    svc = SyncService(kb="local", lance=lance, graph=graph)
    svc.upsert_one({"id": "a.md", "title": "A", "path": "a.md"})
    assert graph.upserts == []


def test_delete_one_forwards_when_enabled():
    lance = FakeLanceStore(ids=[])
    graph = FakeGraphBackend(kb="local", ids=["a.md"])
    svc = SyncService(kb="local", lance=lance, graph=graph)
    svc.delete_one("a.md")
    assert graph.deletes == ["a.md"]
```

Run: `uv run pytest packages/guru-server/tests/test_sync_service.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Add `finalize_indexed_document` to `indexer.py`**

```python
# packages/guru-server/src/guru_server/indexer.py
# ...existing imports...
from guru_server.sync import SyncService


def finalize_indexed_document(sync: SyncService, document: dict) -> None:
    if not sync.graph_enabled():
        return
    sync.upsert_one(document)
```

Find the existing post-LanceDB-upsert call site and invoke `finalize_indexed_document(request.app.state.sync, document)` after LanceDB persistence succeeds.

Add a matching `finalize_deleted_document(sync, doc_id)` and call it from the delete path.

- [ ] **Step 6: Run tests**

```bash
uv run pytest packages/guru-server/tests/test_indexer_sync.py -v
uv run pytest packages/guru-server/tests/ -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/guru-server/src/guru_server/sync.py packages/guru-server/src/guru_server/indexer.py packages/guru-server/src/guru_server/storage.py packages/guru-server/tests/test_sync_service.py packages/guru-server/tests/test_indexer_sync.py
git commit -m "feat(server): mirror ingest/delete into graph via SyncService"
```

---

### Task 1.7: Add `GET /sync/status` and `POST /sync/reconcile`

**Files:**
- Create: `packages/guru-server/src/guru_server/api/sync.py`
- Modify: `packages/guru-server/src/guru_server/app.py`
- Test: `packages/guru-server/tests/test_sync_endpoints.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_sync_endpoints.py
from __future__ import annotations

from fastapi.testclient import TestClient

from guru_server.app import create_app


def test_sync_status_shape(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.get("/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {
        "lancedb_count",
        "graph_count",
        "drift",
        "last_reconciled_at",
        "graph_enabled",
    }


def test_sync_reconcile_heals_drift(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post("/sync/reconcile")
    assert resp.status_code == 200
    assert resp.json()["drift"] == 0


def test_sync_reconcile_409_when_disabled(test_app_graph_disabled):
    client = TestClient(test_app_graph_disabled)
    resp = client.post("/sync/reconcile")
    assert resp.status_code == 409
```

Use existing test fixtures in `packages/guru-server/tests/conftest.py`. If `test_app_with_seed` / `test_app_graph_disabled` don't exist, add them now: seeded LanceDB with two docs, `app.state.sync` points at a `FakeGraphBackend`.

- [ ] **Step 2: Run test — should fail**

Run: `uv run pytest packages/guru-server/tests/test_sync_endpoints.py -v`
Expected: FAIL (404 on both routes).

- [ ] **Step 3: Implement endpoints**

```python
# packages/guru-server/src/guru_server/api/sync.py
from fastapi import APIRouter, HTTPException, Request

from guru_core.graph_types import SyncStatus

router = APIRouter(prefix="/sync")


@router.get("/status", response_model=SyncStatus)
def sync_status(request: Request) -> SyncStatus:
    return request.app.state.sync.status()


@router.post("/reconcile", response_model=SyncStatus)
def sync_reconcile(request: Request) -> SyncStatus:
    sync = request.app.state.sync
    if not sync.graph_enabled():
        raise HTTPException(status_code=409, detail="graph is disabled")
    return sync.reconcile()
```

Register in `app.py` (look for `app.include_router(...)` block):

```python
from guru_server.api import sync as sync_api
app.include_router(sync_api.router)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/guru-server/tests/test_sync_endpoints.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/api/sync.py packages/guru-server/src/guru_server/app.py packages/guru-server/tests/test_sync_endpoints.py packages/guru-server/tests/conftest.py
git commit -m "feat(server): add /sync/status and /sync/reconcile endpoints"
```

---

### Task 1.8: BDD feature `sync_invariant.feature`

**Files:**
- Create: `tests/e2e/features/sync_invariant.feature`
- Create: `tests/e2e/features/steps/sync_steps.py`

- [ ] **Step 1: Write the feature**

```gherkin
# tests/e2e/features/sync_invariant.feature
Feature: LanceDB ↔ graph sync invariant

  Background:
    Given a fresh guru project
    And the graph daemon is enabled

  Scenario: Ingested doc appears in graph
    When I ingest document "a.md"
    Then the graph has a document node "a.md"
    And sync drift is 0

  Scenario: Ingesting with graph disabled leaves drift
    Given the graph daemon is disabled
    When I ingest document "b.md"
    Then sync drift is 1

  Scenario: Enabling the graph heals drift
    Given the graph daemon is disabled
    When I ingest document "c.md"
    And I enable the graph daemon
    And I trigger a reconcile
    Then the graph has a document node "c.md"
    And sync drift is 0

  Scenario: Pruned graph is rebuilt from LanceDB
    When I ingest document "d.md"
    And the graph store is pruned
    And I trigger a reconcile
    Then the graph has a document node "d.md"
    And sync drift is 0

  Scenario: Deleting a document removes the graph node
    Given I ingest document "e.md"
    When I delete document "e.md"
    Then the graph has no document node "e.md"
    And sync drift is 0

  Scenario: Startup reconcile runs when drift exists
    Given the graph store is pruned
    And documents "f.md, g.md" exist in LanceDB
    When the server restarts
    Then sync drift is 0
```

- [ ] **Step 2: Write the step definitions**

```python
# tests/e2e/features/steps/sync_steps.py
from __future__ import annotations

from behave import given, then, when


@given("the graph daemon is enabled")
def step_graph_enabled(context):
    context.guru.set_graph_enabled(True)


@given("the graph daemon is disabled")
def step_graph_disabled(context):
    context.guru.set_graph_enabled(False)


@given('I ingest document "{name}"')
@when('I ingest document "{name}"')
def step_ingest(context, name):
    context.guru.ingest_document(name)


@given('documents "{names}" exist in LanceDB')
def step_ingest_many(context, names):
    for name in [n.strip() for n in names.split(",")]:
        context.guru.ingest_document(name)


@when('I delete document "{name}"')
def step_delete(context, name):
    context.guru.delete_document(name)


@when("I enable the graph daemon")
def step_enable(context):
    context.guru.set_graph_enabled(True)


@when("the graph store is pruned")
@given("the graph store is pruned")
def step_prune(context):
    context.guru.prune_graph()


@when("I trigger a reconcile")
def step_reconcile(context):
    context.guru.reconcile()


@when("the server restarts")
def step_restart(context):
    context.guru.restart_server()


@then('the graph has a document node "{name}"')
def step_assert_graph_has(context, name):
    assert name in context.guru.list_graph_document_ids()


@then('the graph has no document node "{name}"')
def step_assert_graph_hasnt(context, name):
    assert name not in context.guru.list_graph_document_ids()


@then("sync drift is {n:d}")
def step_drift(context, n):
    assert context.guru.sync_status().drift == n
```

The `context.guru` is the existing harness in `tests/e2e/features/environment.py`. Extend it with the new methods (`ingest_document`, `delete_document`, `set_graph_enabled`, `prune_graph`, `reconcile`, `list_graph_document_ids`, `sync_status`, `restart_server`). Each is a thin HTTP call to the running server via the existing Python HTTP client; `prune_graph` clears graph docs via a test-only backend method or by truncating the graph socket file's test Neo4j instance.

- [ ] **Step 3: Run the feature**

```bash
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/sync_invariant.feature
```

Expected: 6 scenarios pass. Some may require marking `@real_neo4j` and running with Neo4j available (`./scripts/start-test-neo4j.sh`).

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/features/sync_invariant.feature tests/e2e/features/steps/sync_steps.py tests/e2e/features/environment.py
git commit -m "test(e2e): BDD coverage for LanceDB↔graph sync invariant"
```

---

## Phase 2 — Supporting endpoints for the web UI

### Task 2.1: Add `POST /documents/search`

**Files:**
- Modify: `packages/guru-server/src/guru_server/api/documents.py`
- Modify: `packages/guru-server/src/guru_server/api/models.py` (add `DocumentSearchHit` response model if not using `guru_core` directly)
- Test: `packages/guru-server/tests/test_documents_search.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_documents_search.py
from fastapi.testclient import TestClient

from guru_server.app import create_app


def test_documents_search_returns_ranked_hits(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post("/documents/search", json={"query": "readme", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "hits" in body
    assert len(body["hits"]) <= 5
    if body["hits"]:
        first = body["hits"][0]
        assert set(first.keys()) >= {"path", "title", "excerpt", "score"}
        assert isinstance(first["score"], float)


def test_documents_search_rejects_empty_query(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post("/documents/search", json={"query": "", "limit": 5})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test — should fail**

Run: `uv run pytest packages/guru-server/tests/test_documents_search.py -v`
Expected: 404.

- [ ] **Step 3: Implement**

In `packages/guru-server/src/guru_server/api/documents.py`:

```python
from pydantic import BaseModel, Field, constr

from guru_core.graph_types import DocumentSearchHit


class DocumentSearchBody(BaseModel):
    query: constr(min_length=1, max_length=500)  # type: ignore[valid-type]
    limit: int = Field(20, ge=1, le=100)


class DocumentSearchResponse(BaseModel):
    hits: list[DocumentSearchHit]


@router.post("/documents/search", response_model=DocumentSearchResponse)
async def documents_search(body: DocumentSearchBody, request: Request) -> DocumentSearchResponse:
    store = request.app.state.store
    embedder = request.app.state.embedder

    query_vector = await embedder.embed(body.query)
    rows = store.search(query_vector=query_vector, n_results=body.limit)

    hits: list[DocumentSearchHit] = []
    seen_paths: set[str] = set()
    for row in rows:
        path = row["path"]
        if path in seen_paths:
            continue
        seen_paths.add(path)
        hits.append(
            DocumentSearchHit(
                path=path,
                title=row.get("title", path),
                excerpt=row.get("excerpt") or row.get("text", "")[:200],
                score=float(row["score"]),
            )
        )
    return DocumentSearchResponse(hits=hits)
```

The collapse-by-path step is essential: the raw similarity search returns one row per chunk; we want one hit per document.

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/guru-server/tests/test_documents_search.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/api/documents.py packages/guru-server/tests/test_documents_search.py
git commit -m "feat(server): add POST /documents/search with doc-collapsed hits"
```

---

### Task 2.2: Add `GET /graph/roots`

**Files:**
- Modify: `packages/guru-server/src/guru_server/api/graph.py`
- Test: `packages/guru-server/tests/test_graph_roots.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_graph_roots.py
from fastapi.testclient import TestClient


def test_graph_roots_returns_federation_and_kbs(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.get("/graph/roots")
    assert resp.status_code == 200
    body = resp.json()
    assert body["federation_root"] == {"id": "federation", "label": "Federation"}
    assert isinstance(body["kbs"], list)
    assert len(body["kbs"]) >= 1
    assert {"name", "project_root"} <= set(body["kbs"][0].keys())


def test_graph_roots_returns_410_when_graph_disabled(test_app_graph_disabled):
    client = TestClient(test_app_graph_disabled)
    resp = client.get("/graph/roots")
    assert resp.status_code == 410
    assert resp.json()["detail"] == "graph is disabled"
```

- [ ] **Step 2: Run — should fail**

Run: `uv run pytest packages/guru-server/tests/test_graph_roots.py -v`
Expected: 404.

- [ ] **Step 3: Implement**

Append to `packages/guru-server/src/guru_server/api/graph.py`:

```python
from guru_core.graph_types import FederationRootNode, GraphRootsPayload


@router.get("/graph/roots", response_model=GraphRootsPayload)
def graph_roots(request: Request) -> GraphRootsPayload:
    graph_client = request.app.state.graph_client
    if not graph_client.is_available():
        raise HTTPException(status_code=410, detail="graph is disabled")

    local_kb = graph_client.get_kb(request.app.state.config.kb_name)
    federated = [
        graph_client.get_kb(name)
        for name in request.app.state.federation_registry.list_names()
        if name != request.app.state.config.kb_name
    ]
    kbs = [kb for kb in [local_kb, *federated] if kb is not None]
    return GraphRootsPayload(federation_root=FederationRootNode(), kbs=kbs)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/guru-server/tests/test_graph_roots.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/api/graph.py packages/guru-server/tests/test_graph_roots.py
git commit -m "feat(server): add GET /graph/roots with federation+kbs payload"
```

---

### Task 2.3: Filter neighbors payload to document-kind nodes

**Files:**
- Modify: `packages/guru-server/src/guru_server/api/graph.py` (neighbors handler)
- Test: `packages/guru-server/tests/test_graph_neighbors_filter.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_graph_neighbors_filter.py
from fastapi.testclient import TestClient


def test_neighbors_are_filtered_to_document_kind(test_app_with_mixed_graph):
    """Graph contains one doc node + one code-artifact node; response has only the doc."""
    client = TestClient(test_app_with_mixed_graph)
    resp = client.get("/graph/neighbors/doc:a.md")
    assert resp.status_code == 200
    body = resp.json()
    kinds = {node["kind"] for node in body["nodes"]}
    assert kinds.issubset({"document", "kb"})
```

Add `test_app_with_mixed_graph` fixture to `conftest.py`: seeds one `:Document` node + one `:Artifact` (python_function) node, returns the app.

- [ ] **Step 2: Run — should fail**

Run: `uv run pytest packages/guru-server/tests/test_graph_neighbors_filter.py -v`
Expected: FAIL, artifact leaks through.

- [ ] **Step 3: Apply server-side filter**

In the neighbors route in `packages/guru-server/src/guru_server/api/graph.py`, post-process the response:

```python
_WEB_ALLOWED_KINDS = {"document", "kb"}


@router.get("/graph/neighbors/{node_id}")
def graph_neighbors(node_id: str, request: Request):
    graph_client = request.app.state.graph_client
    if not graph_client.is_available():
        return {"status": "graph_disabled"}
    payload = graph_client.neighbors(node_id)
    nodes = [n for n in payload.get("nodes", []) if n.get("kind") in _WEB_ALLOWED_KINDS]
    kept_ids = {n["id"] for n in nodes}
    edges = [
        e for e in payload.get("edges", [])
        if e.get("source") in kept_ids and e.get("target") in kept_ids
    ]
    return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/guru-server/tests/test_graph_neighbors_filter.py -v`
Expected: PASS.

Also run the existing `packages/guru-server/tests/` suite to confirm no regressions.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/api/graph.py packages/guru-server/tests/test_graph_neighbors_filter.py packages/guru-server/tests/conftest.py
git commit -m "feat(server): filter graph neighbors to document+kb kinds for web"
```

---

### Task 2.4: Standardise `POST /graph/query` response shape

**Files:**
- Modify: `packages/guru-server/src/guru_server/api/graph.py`
- Modify: `packages/guru-server/src/guru_server/api/models.py`
- Test: `packages/guru-server/tests/test_graph_query_shape.py` (create)

- [ ] **Step 1: Write failing test**

```python
# packages/guru-server/tests/test_graph_query_shape.py
from fastapi.testclient import TestClient


def test_graph_query_returns_nodes_and_edges(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MATCH (d:Document) RETURN d LIMIT 5"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"nodes", "edges"}
    for node in body["nodes"]:
        assert {"id", "label", "kind", "kb"} <= set(node.keys())
    for edge in body["edges"]:
        assert {"source", "target", "kind"} <= set(edge.keys())


def test_graph_query_never_returns_federation_root(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post(
        "/graph/query",
        json={"cypher": "MATCH (n) RETURN n"},
    )
    body = resp.json()
    assert all(n["id"] != "federation" for n in body["nodes"])


def test_graph_query_rejects_writes(test_app_with_seed):
    client = TestClient(test_app_with_seed)
    resp = client.post(
        "/graph/query",
        json={"cypher": "CREATE (:Document {id: 'x.md'}) RETURN 1"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run — should fail**

Run: `uv run pytest packages/guru-server/tests/test_graph_query_shape.py -v`
Expected: shape mismatch or write acceptance.

- [ ] **Step 3: Implement**

Add response models to `api/models.py`:

```python
class GraphNodeOut(BaseModel):
    id: str
    label: str
    kind: str
    kb: str | None = None


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    kind: str


class GraphQueryResult(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
```

Rewrite the `POST /graph/query` handler in `api/graph.py` to:
1. Refuse any cypher containing `CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, `DETACH` (case-insensitive, word-boundary regex).
2. Execute via `graph_client.query(cypher)`.
3. Walk the result rows to accumulate `{id, label, kind, kb}` nodes and `{source, target, kind}` edges.
4. Drop any node whose `id == "federation"`.

```python
import re

_WRITE_RE = re.compile(r"\b(create|merge|delete|set|remove|detach)\b", re.IGNORECASE)


@router.post("/graph/query", response_model=GraphQueryResult)
def graph_query(body: GraphQueryBody, request: Request) -> GraphQueryResult:
    if _WRITE_RE.search(body.cypher):
        raise HTTPException(status_code=400, detail="writes are not permitted")
    graph_client = request.app.state.graph_client
    if not graph_client.is_available():
        raise HTTPException(status_code=410, detail="graph is disabled")

    raw = graph_client.query(body.cypher)

    nodes: dict[str, GraphNodeOut] = {}
    edges: list[GraphEdgeOut] = []
    for row in raw:
        for node in row.get("nodes", []):
            if node["id"] == "federation":
                continue
            if node["id"] not in nodes:
                nodes[node["id"]] = GraphNodeOut(
                    id=node["id"],
                    label=node.get("label", node["id"]),
                    kind=node.get("kind", "unknown"),
                    kb=node.get("kb"),
                )
        for edge in row.get("edges", []):
            edges.append(GraphEdgeOut(**edge))

    return GraphQueryResult(nodes=list(nodes.values()), edges=edges)
```

Adjust `graph_client.query()` in `packages/guru-core/src/guru_core/client.py` if it doesn't already emit `{nodes: [...], edges: [...]}` per row. If not, push the extraction into the graph daemon's `/graph/query` handler rather than the server. Pick one place.

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/guru-server/tests/test_graph_query_shape.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/api/graph.py packages/guru-server/src/guru_server/api/models.py packages/guru-server/tests/test_graph_query_shape.py packages/guru-core/src/guru_core/client.py
git commit -m "feat(server): standardise /graph/query response as {nodes, edges}"
```

---

## Phase 3 — Web UI shell refactor

### Task 3.1: Remove hardcoded mocks from `workbench.ts`

**Files:**
- Modify: `packages/guru-web/src/lib/state/workbench.ts`
- Modify: `packages/guru-web/src/lib/state/url.ts`
- Test: `packages/guru-web/src/lib/state/workbench.test.ts` (create)

- [ ] **Step 1: Write failing test**

```ts
// packages/guru-web/src/lib/state/workbench.test.ts
import { describe, expect, it } from "vitest";

import { useWorkbench } from "./workbench";
import { workbenchSurfaces } from "./url";

describe("workbench store", () => {
  it("surfaces are exactly documents, graph, status", () => {
    expect(workbenchSurfaces).toEqual(["documents", "graph", "status"]);
  });

  it("has no hardcoded entity or investigation mock data", () => {
    const state = useWorkbench.getState() as unknown as Record<string, unknown>;
    expect(state).not.toHaveProperty("workbenchEntities");
    expect(state).not.toHaveProperty("investigateResults");
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd packages/guru-web && npm test -- --run workbench.test`
Expected: FAIL (surfaces still `investigate/graph/query/operate`, mocks present).

- [ ] **Step 3: Rewrite `url.ts` surface enum**

```ts
// packages/guru-web/src/lib/state/url.ts
export const workbenchSurfaces = ["documents", "graph", "status"] as const;
export type WorkbenchSurface = (typeof workbenchSurfaces)[number];

export const surfaceToPath: Record<WorkbenchSurface, string> = {
  documents: "/documents",
  graph: "/graph",
  status: "/status",
};

export const surfaceLabels: Record<WorkbenchSurface, string> = {
  documents: "Documents",
  graph: "Graph",
  status: "Status",
};
```

- [ ] **Step 4: Purge mocks from `workbench.ts`**

Delete `workbenchEntities` (lines 41–69), `investigateResults` (lines 40–103), all references in the Zustand store. The store becomes:

```ts
// packages/guru-web/src/lib/state/workbench.ts
import { create } from "zustand";

import type { WorkbenchSurface } from "./url";
import type { BootPayload } from "../api/types";

interface WorkbenchState {
  boot: BootPayload;
  surface: WorkbenchSurface;
  selectedDocumentPath: string | null;
  selectedGraphNodeId: string | null;
  rightPaneOpen: Record<WorkbenchSurface, boolean>;

  setSurface: (s: WorkbenchSurface) => void;
  selectDocument: (path: string | null) => void;
  selectGraphNode: (id: string | null) => void;
  toggleRightPane: (s: WorkbenchSurface) => void;
  setBoot: (b: BootPayload) => void;
}

function loadPaneState(): Record<WorkbenchSurface, boolean> {
  try {
    const raw = localStorage.getItem("guru.workbench.paneState");
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore
  }
  return { documents: true, graph: true, status: false };
}

function savePaneState(state: Record<WorkbenchSurface, boolean>) {
  try {
    localStorage.setItem("guru.workbench.paneState", JSON.stringify(state));
  } catch {
    // ignore
  }
}

export const useWorkbench = create<WorkbenchState>((set) => ({
  boot: { project: { name: "", root: "" }, web: { enabled: true, available: true, reason: null }, graph: { enabled: false } },
  surface: "documents",
  selectedDocumentPath: null,
  selectedGraphNodeId: null,
  rightPaneOpen: loadPaneState(),

  setSurface: (s) => set({ surface: s }),
  selectDocument: (path) => set({ selectedDocumentPath: path }),
  selectGraphNode: (id) => set({ selectedGraphNodeId: id }),
  toggleRightPane: (s) => set((prev) => {
    const next = { ...prev.rightPaneOpen, [s]: !prev.rightPaneOpen[s] };
    savePaneState(next);
    return { rightPaneOpen: next };
  }),
  setBoot: (b) => set({ boot: b }),
}));
```

Delete any `workbench.test.tsx` assertions that referenced the old shape; update `App.test.tsx` and `AppShell.test.tsx` to the new surface names where needed.

- [ ] **Step 5: Run tests**

Run: `cd packages/guru-web && npm test -- --run`
Expected: all pass. Compile errors in pages that still import `workbenchEntities` are expected — they will be cleaned up in the next tasks. For this task, temporarily comment out the offending imports in `InvestigatePage.tsx`, `GraphPage.tsx`, `QueryPage.tsx`, `OperatePage.tsx`, and `Inspector.tsx` to make the test suite pass. Mark each such file with `// TODO(phase 3 task N): remove` to track.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web/src/lib/state/
git commit -m "refactor(web): purge workbench mocks; surfaces=documents/graph/status"
```

---

### Task 3.2: New `AppShell` with top menu bar and closeable right pane

**Files:**
- Modify: `packages/guru-web/src/app/layout/AppShell.tsx`
- Modify: `packages/guru-web/src/app/router.tsx`
- Create: `packages/guru-web/src/app/layout/MenuBar.tsx`
- Create: `packages/guru-web/src/app/layout/RightPane.tsx`
- Test: `packages/guru-web/src/app/AppShell.test.tsx` (rewrite)

- [ ] **Step 1: Write failing test**

```tsx
// packages/guru-web/src/app/AppShell.test.tsx
import { describe, expect, it } from "vitest";
import { screen, fireEvent } from "@testing-library/react";

import { renderWithRouter } from "../test/render";
import { AppShell } from "./layout/AppShell";

describe("AppShell", () => {
  it("renders three menu items", () => {
    renderWithRouter(<AppShell />);
    expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Graph" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Status" })).toBeInTheDocument();
  });

  it("does not render legacy Investigate/Query/Operate", () => {
    renderWithRouter(<AppShell />);
    expect(screen.queryByText("Investigate")).toBeNull();
    expect(screen.queryByText("Query")).toBeNull();
    expect(screen.queryByText("Operate")).toBeNull();
  });

  it("right pane toggles via button and persists in localStorage", () => {
    renderWithRouter(<AppShell />, { route: "/documents" });
    const toggle = screen.getByRole("button", { name: /toggle metadata/i });
    fireEvent.click(toggle);
    expect(JSON.parse(localStorage.getItem("guru.workbench.paneState") || "{}").documents).toBe(false);
  });

  it("main area has no max-width constraint", () => {
    const { container } = renderWithRouter(<AppShell />);
    const main = container.querySelector("[data-surface-main]");
    expect(main).toBeTruthy();
    const cs = getComputedStyle(main!);
    expect(cs.maxWidth === "none" || cs.maxWidth === "" || cs.maxWidth.endsWith("%")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd packages/guru-web && npm test -- --run AppShell.test`
Expected: FAIL.

- [ ] **Step 3: Implement `MenuBar`**

```tsx
// packages/guru-web/src/app/layout/MenuBar.tsx
import { NavLink } from "react-router-dom";

import { workbenchSurfaces, surfaceToPath, surfaceLabels } from "../../lib/state/url";
import { cn } from "../../lib/utils";

export function MenuBar({ projectName }: { projectName: string }) {
  return (
    <nav
      className="flex h-8 items-center gap-4 border-b border-neutral-200 bg-white px-4 text-sm"
      aria-label="Primary"
    >
      <span className="font-semibold text-neutral-700" data-testid="project-name">{projectName}</span>
      <ul className="flex items-center gap-3">
        {workbenchSurfaces.map((s) => (
          <li key={s}>
            <NavLink
              to={surfaceToPath[s]}
              className={({ isActive }) =>
                cn(
                  "rounded px-2 py-1 text-neutral-600 hover:bg-neutral-100",
                  isActive && "bg-neutral-900 text-white hover:bg-neutral-900",
                )
              }
            >
              {surfaceLabels[s]}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

- [ ] **Step 4: Implement `RightPane`**

```tsx
// packages/guru-web/src/app/layout/RightPane.tsx
import { useWorkbench } from "../../lib/state/workbench";

export function RightPane({ children }: { children: React.ReactNode }) {
  const surface = useWorkbench((s) => s.surface);
  const isOpen = useWorkbench((s) => s.rightPaneOpen[surface]);
  const toggle = useWorkbench((s) => s.toggleRightPane);

  return (
    <aside
      className={isOpen ? "w-80 border-l border-neutral-200 bg-white" : "w-8 border-l border-neutral-200 bg-neutral-50"}
      aria-label="Metadata"
    >
      <div className="flex items-center justify-between p-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
          {isOpen ? "Metadata" : ""}
        </span>
        <button
          type="button"
          aria-label="Toggle metadata pane"
          onClick={() => toggle(surface)}
          className="rounded p-1 text-neutral-500 hover:bg-neutral-100"
        >
          {isOpen ? "›" : "‹"}
        </button>
      </div>
      {isOpen ? <div className="p-3">{children}</div> : null}
    </aside>
  );
}
```

- [ ] **Step 5: Rewrite `AppShell`**

```tsx
// packages/guru-web/src/app/layout/AppShell.tsx
import { Outlet } from "react-router-dom";

import { useWorkbench } from "../../lib/state/workbench";
import { MenuBar } from "./MenuBar";

export function AppShell() {
  const boot = useWorkbench((s) => s.boot);
  return (
    <div className="flex h-screen flex-col bg-neutral-50">
      <MenuBar projectName={boot.project.name} />
      <main data-surface-main className="flex min-h-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 6: Update `router.tsx`**

```tsx
// packages/guru-web/src/app/router.tsx
import { createBrowserRouter, Navigate } from "react-router-dom";

import { DocumentsPage } from "../features/documents/DocumentsPage";
import { GraphPage } from "../features/graph/GraphPage";
import { StatusPage } from "../features/status/StatusPage";
import { AppShell } from "./layout/AppShell";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/documents" replace /> },
      { path: "documents", element: <DocumentsPage /> },
      { path: "documents/*", element: <DocumentsPage /> },
      { path: "graph", element: <GraphPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "*", element: <Navigate to="/documents" replace /> },
    ],
  },
]);
```

Create placeholder `DocumentsPage`, `StatusPage` (stubs returning `<div>TODO</div>` — real implementations come in Phase 4/6). Delete `InvestigatePage.tsx`, `OperatePage.tsx`, `QueryPage.tsx` and their tests in this commit — or mark them with `@ts-nocheck` and remove in Phase 4.

```tsx
// packages/guru-web/src/features/documents/DocumentsPage.tsx
export function DocumentsPage() {
  return <div data-testid="documents-surface" className="flex-1" />;
}

// packages/guru-web/src/features/status/StatusPage.tsx
export function StatusPage() {
  return <div data-testid="status-surface" className="flex-1" />;
}
```

- [ ] **Step 7: Run tests**

Run: `cd packages/guru-web && npm test -- --run`
Expected: `AppShell.test`, `workbench.test`, existing smoke all pass. Legacy page tests referring to InvestigatePage/QueryPage/OperatePage should be deleted.

- [ ] **Step 8: Commit**

```bash
git add packages/guru-web/src/
git rm packages/guru-web/src/features/investigate/ packages/guru-web/src/features/query/ packages/guru-web/src/features/operate/ packages/guru-web/src/features/knowledge-tree/
git commit -m "refactor(web): replace AppShell with menu bar + closeable pane; remove legacy surfaces"
```

---

## Phase 4 — Documents surface

### Task 4.1: `DocumentList` component bound to `GET /documents`

**Files:**
- Create: `packages/guru-web/src/features/documents/DocumentList.tsx`
- Create: `packages/guru-web/src/features/documents/DocumentList.test.tsx`
- Modify: `packages/guru-web/src/lib/api/hooks.ts` (add `useDocuments`)

- [ ] **Step 1: Write failing test**

```tsx
// packages/guru-web/src/features/documents/DocumentList.test.tsx
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { renderWithRouter } from "../../test/render";
import { DocumentList } from "./DocumentList";
import { mockServer } from "../../test/msw";

describe("DocumentList", () => {
  it("renders items from GET /documents", async () => {
    mockServer.use(
      rest.get("/documents", (_, res, ctx) =>
        res(ctx.json([{ path: "a.md", title: "Alpha", excerpt: "a ex" }])),
      ),
    );
    renderWithRouter(<DocumentList onSelect={() => {}} selectedPath={null} />);
    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());
  });

  it("highlights the selected row", async () => {
    mockServer.use(
      rest.get("/documents", (_, res, ctx) =>
        res(ctx.json([{ path: "a.md", title: "Alpha", excerpt: "a ex" }])),
      ),
    );
    renderWithRouter(<DocumentList onSelect={() => {}} selectedPath="a.md" />);
    const row = await screen.findByRole("listitem", { name: /alpha/i });
    expect(row.getAttribute("aria-selected")).toBe("true");
  });
});
```

If MSW isn't set up, add it as a dev dep (`npm install -D msw`) and create `packages/guru-web/src/test/msw.ts` with a bootstrapped server and a `beforeAll`/`afterAll` wiring in `test/setup.ts`.

- [ ] **Step 2: Run — should fail**

Run: `cd packages/guru-web && npm test -- --run DocumentList.test`
Expected: FAIL.

- [ ] **Step 3: Implement hook**

```ts
// packages/guru-web/src/lib/api/hooks.ts (append)
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "./client";

export interface DocumentListItem {
  path: string;
  title: string;
  excerpt: string;
}

export function useDocuments() {
  return useQuery<DocumentListItem[]>({
    queryKey: ["documents"],
    queryFn: async () => {
      const resp = await apiClient.get<DocumentListItem[]>("/documents");
      return resp;
    },
  });
}
```

If `@tanstack/react-query` is not yet a dep, add it (`npm install @tanstack/react-query`). Ensure `providers.tsx` wraps the app in a `QueryClientProvider`.

- [ ] **Step 4: Implement `DocumentList`**

```tsx
// packages/guru-web/src/features/documents/DocumentList.tsx
import { useDocuments } from "../../lib/api/hooks";

export function DocumentList({
  onSelect,
  selectedPath,
}: {
  onSelect: (path: string) => void;
  selectedPath: string | null;
}) {
  const { data, isLoading, isError } = useDocuments();
  if (isLoading) return <div className="p-3 text-sm text-neutral-500">Loading…</div>;
  if (isError) return <div className="p-3 text-sm text-red-600">Failed to load documents.</div>;
  return (
    <ul className="divide-y divide-neutral-200">
      {(data ?? []).map((doc) => (
        <li
          key={doc.path}
          aria-label={doc.title}
          aria-selected={doc.path === selectedPath}
          role="listitem"
          onClick={() => onSelect(doc.path)}
          className={
            "cursor-pointer p-3 text-sm " +
            (doc.path === selectedPath ? "bg-neutral-900 text-white" : "hover:bg-neutral-100")
          }
        >
          <div className="font-medium">{doc.title}</div>
          <div className="text-xs text-neutral-500">{doc.excerpt}</div>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 5: Run tests**

Run: `cd packages/guru-web && npm test -- --run DocumentList.test`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web/src/features/documents/ packages/guru-web/src/lib/api/hooks.ts packages/guru-web/src/test/msw.ts
git commit -m "feat(web): DocumentList bound to GET /documents"
```

---

### Task 4.2: `DocumentSearchBox` bound to `POST /documents/search`

**Files:**
- Create: `packages/guru-web/src/features/documents/DocumentSearchBox.tsx`
- Create: `packages/guru-web/src/features/documents/DocumentSearchBox.test.tsx`
- Modify: `packages/guru-web/src/lib/api/hooks.ts`

- [ ] **Step 1: Write failing test**

```tsx
// packages/guru-web/src/features/documents/DocumentSearchBox.test.tsx
import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { rest } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { DocumentSearchBox } from "./DocumentSearchBox";

describe("DocumentSearchBox", () => {
  it("calls onResults with hits when query submitted", async () => {
    mockServer.use(
      rest.post("/documents/search", (_, res, ctx) =>
        res(ctx.json({ hits: [{ path: "a.md", title: "A", excerpt: "hit", score: 0.9 }] })),
      ),
    );
    const onResults = vi.fn();
    renderWithRouter(<DocumentSearchBox onResults={onResults} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "foo" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(onResults).toHaveBeenCalled());
    expect(onResults.mock.calls[0][0][0]).toEqual({
      path: "a.md",
      title: "A",
      excerpt: "hit",
      score: 0.9,
    });
  });

  it("clears results when input emptied", async () => {
    const onResults = vi.fn();
    renderWithRouter(<DocumentSearchBox onResults={onResults} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "" } });
    expect(onResults).toHaveBeenLastCalledWith(null);
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd packages/guru-web && npm test -- --run DocumentSearchBox.test`
Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// packages/guru-web/src/lib/api/hooks.ts (append)
export interface DocumentSearchHit {
  path: string;
  title: string;
  excerpt: string;
  score: number;
}

export async function searchDocuments(query: string, limit = 20): Promise<DocumentSearchHit[]> {
  const resp = await apiClient.post<{ hits: DocumentSearchHit[] }>("/documents/search", {
    query,
    limit,
  });
  return resp.hits;
}
```

```tsx
// packages/guru-web/src/features/documents/DocumentSearchBox.tsx
import { useState } from "react";

import { DocumentSearchHit, searchDocuments } from "../../lib/api/hooks";

export function DocumentSearchBox({
  onResults,
}: {
  onResults: (hits: DocumentSearchHit[] | null) => void;
}) {
  const [q, setQ] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!q.trim()) {
      onResults(null);
      return;
    }
    const hits = await searchDocuments(q.trim());
    onResults(hits);
  }

  return (
    <form role="search" onSubmit={submit} className="flex items-center gap-2 border-b border-neutral-200 p-2">
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          if (!e.target.value) onResults(null);
        }}
        placeholder="Search documents (similarity)"
        className="flex-1 rounded border border-neutral-300 px-2 py-1 text-sm"
      />
      <button
        type="submit"
        className="rounded bg-neutral-900 px-2 py-1 text-sm text-white hover:bg-neutral-700"
      >
        Search
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd packages/guru-web && npm test -- --run DocumentSearchBox.test`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/src/features/documents/DocumentSearchBox.tsx packages/guru-web/src/features/documents/DocumentSearchBox.test.tsx packages/guru-web/src/lib/api/hooks.ts
git commit -m "feat(web): DocumentSearchBox bound to POST /documents/search"
```

---

### Task 4.3: `DocumentDetail` component with markdown render + "Go to graph"

**Files:**
- Create: `packages/guru-web/src/features/documents/DocumentDetail.tsx`
- Create: `packages/guru-web/src/features/documents/DocumentDetail.test.tsx`
- Modify: `packages/guru-web/src/lib/api/hooks.ts`

Add a `react-markdown` dep if absent (`npm install react-markdown remark-gfm`).

- [ ] **Step 1: Write failing test**

```tsx
// packages/guru-web/src/features/documents/DocumentDetail.test.tsx
import { describe, expect, it } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { rest } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { DocumentDetail } from "./DocumentDetail";

describe("DocumentDetail", () => {
  it("renders markdown content", async () => {
    mockServer.use(
      rest.get("/documents/a.md", (_, res, ctx) =>
        res(ctx.json({ path: "a.md", title: "A", content: "# Hello\n\n**world**" })),
      ),
    );
    renderWithRouter(<DocumentDetail path="a.md" />);
    expect(await screen.findByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("world").tagName).toBe("STRONG");
  });

  it("Go to graph button navigates and focuses node", async () => {
    mockServer.use(
      rest.get("/documents/a.md", (_, res, ctx) =>
        res(ctx.json({ path: "a.md", title: "A", content: "x" })),
      ),
    );
    const { router } = renderWithRouter(<DocumentDetail path="a.md" />);
    fireEvent.click(await screen.findByRole("button", { name: /go to graph/i }));
    expect(router.state.location.pathname).toBe("/graph");
    expect(router.state.location.search).toBe("?focus=doc%3Aa.md");
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd packages/guru-web && npm test -- --run DocumentDetail.test`
Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// hooks.ts — add useDocument
export interface DocumentOut {
  path: string;
  title: string;
  content: string;
}

export function useDocument(path: string | null) {
  return useQuery<DocumentOut | null>({
    queryKey: ["document", path],
    queryFn: async () => {
      if (!path) return null;
      return apiClient.get<DocumentOut>(`/documents/${encodeURIComponent(path)}`);
    },
    enabled: !!path,
  });
}
```

```tsx
// DocumentDetail.tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate } from "react-router-dom";

import { useDocument } from "../../lib/api/hooks";

export function DocumentDetail({ path }: { path: string }) {
  const { data, isLoading } = useDocument(path);
  const navigate = useNavigate();
  if (isLoading) return <div className="p-6 text-sm text-neutral-500">Loading…</div>;
  if (!data) return null;
  return (
    <article className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 p-4">
        <h1 className="text-xl font-semibold">{data.title}</h1>
        <button
          type="button"
          onClick={() => navigate(`/graph?focus=${encodeURIComponent(`doc:${data.path}`)}`)}
          className="rounded bg-neutral-900 px-3 py-1 text-sm text-white hover:bg-neutral-700"
        >
          Go to graph
        </button>
      </header>
      <div className="flex-1 overflow-auto p-6 prose prose-neutral max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.content}</ReactMarkdown>
      </div>
    </article>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd packages/guru-web && npm test -- --run DocumentDetail.test`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/src/features/documents/ packages/guru-web/src/lib/api/hooks.ts packages/guru-web/package.json packages/guru-web/package-lock.json
git commit -m "feat(web): DocumentDetail with markdown render and Go to graph"
```

---

### Task 4.4: `DocumentMetaPane` with LanceDB + graph sections

**Files:**
- Create: `packages/guru-web/src/features/documents/DocumentMetaPane.tsx`
- Create: `packages/guru-web/src/features/documents/DocumentMetaPane.test.tsx`
- Modify: `packages/guru-web/src/lib/api/hooks.ts`

- [ ] **Step 1: Write failing test**

```tsx
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { rest } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { DocumentMetaPane } from "./DocumentMetaPane";

describe("DocumentMetaPane", () => {
  it("shows LanceDB and Graph sections when graph enabled", async () => {
    mockServer.use(
      rest.get("/documents/a.md/metadata", (_, res, ctx) =>
        res(ctx.json({
          lance: { path: "a.md", chunk_count: 3, token_count: 42, tags: ["foo"], ingested_at: "2026-04-19T00:00:00Z" },
          graph: { node_id: "doc:a.md", degree: 2, links: [{ kind: "DEPENDS_ON", target: "b.md" }] },
        })),
      ),
    );
    renderWithRouter(<DocumentMetaPane path="a.md" graphEnabled={true} />);
    expect(await screen.findByText("LanceDB")).toBeInTheDocument();
    expect(screen.getByText("Graph")).toBeInTheDocument();
    expect(screen.getByText("chunks")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("hides Graph section when graph disabled", async () => {
    mockServer.use(
      rest.get("/documents/a.md/metadata", (_, res, ctx) =>
        res(ctx.json({
          lance: { path: "a.md", chunk_count: 1, token_count: 1, tags: [], ingested_at: null },
          graph: null,
        })),
      ),
    );
    renderWithRouter(<DocumentMetaPane path="a.md" graphEnabled={false} />);
    await screen.findByText("LanceDB");
    expect(screen.queryByText("Graph")).toBeNull();
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL (no component, no endpoint wired).

- [ ] **Step 3: Add `/documents/{path}/metadata` server endpoint**

In `packages/guru-server/src/guru_server/api/documents.py`:

```python
class DocumentLanceMeta(BaseModel):
    path: str
    chunk_count: int
    token_count: int
    tags: list[str]
    ingested_at: str | None


class DocumentGraphMeta(BaseModel):
    node_id: str
    degree: int
    links: list[dict]


class DocumentMetadataOut(BaseModel):
    lance: DocumentLanceMeta
    graph: DocumentGraphMeta | None


@router.get("/documents/{path:path}/metadata", response_model=DocumentMetadataOut)
def document_metadata(path: str, request: Request):
    store = request.app.state.store
    row = store.get_document_summary(path)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    lance = DocumentLanceMeta(
        path=path,
        chunk_count=row["chunk_count"],
        token_count=row["token_count"],
        tags=row.get("tags", []),
        ingested_at=row.get("ingested_at"),
    )

    graph_client = request.app.state.graph_client
    if graph_client.is_available():
        node = graph_client.describe(f"doc:{path}")
        graph = DocumentGraphMeta(
            node_id=node["id"],
            degree=node.get("degree", 0),
            links=node.get("links", []),
        )
    else:
        graph = None
    return DocumentMetadataOut(lance=lance, graph=graph)
```

Add an in-server unit test at `packages/guru-server/tests/test_documents_metadata.py` covering the shape.

- [ ] **Step 4: Implement `DocumentMetaPane`**

```tsx
// DocumentMetaPane.tsx
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../../lib/api/client";

interface MetaPayload {
  lance: { path: string; chunk_count: number; token_count: number; tags: string[]; ingested_at: string | null };
  graph: { node_id: string; degree: number; links: { kind: string; target: string }[] } | null;
}

export function DocumentMetaPane({ path, graphEnabled }: { path: string; graphEnabled: boolean }) {
  const { data, isLoading } = useQuery<MetaPayload>({
    queryKey: ["doc-meta", path],
    queryFn: async () => apiClient.get<MetaPayload>(`/documents/${encodeURIComponent(path)}/metadata`),
    enabled: !!path,
  });
  if (isLoading || !data) return <div className="text-sm text-neutral-500">Loading…</div>;
  return (
    <div className="space-y-4 text-sm">
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">LanceDB</h3>
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-neutral-700">
          <dt>path</dt><dd>{data.lance.path}</dd>
          <dt>chunks</dt><dd>{data.lance.chunk_count}</dd>
          <dt>tokens</dt><dd>{data.lance.token_count}</dd>
          <dt>tags</dt><dd>{data.lance.tags.join(", ") || "—"}</dd>
          <dt>ingested</dt><dd>{data.lance.ingested_at ?? "—"}</dd>
        </dl>
      </section>
      {graphEnabled && data.graph ? (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">Graph</h3>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-neutral-700">
            <dt>node</dt><dd>{data.graph.node_id}</dd>
            <dt>degree</dt><dd>{data.graph.degree}</dd>
          </dl>
          {data.graph.links.length > 0 ? (
            <ul className="mt-2 space-y-1">
              {data.graph.links.map((l, i) => (
                <li key={i}><span className="text-neutral-500">{l.kind}</span> → {l.target}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Run tests**

```bash
cd packages/guru-web && npm test -- --run DocumentMetaPane.test
uv run pytest packages/guru-server/tests/test_documents_metadata.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web/src/features/documents/DocumentMetaPane.tsx packages/guru-web/src/features/documents/DocumentMetaPane.test.tsx packages/guru-server/src/guru_server/api/documents.py packages/guru-server/tests/test_documents_metadata.py
git commit -m "feat: DocumentMetaPane with LanceDB + graph meta"
```

---

### Task 4.5: Compose the `DocumentsPage` three-pane layout

**Files:**
- Modify: `packages/guru-web/src/features/documents/DocumentsPage.tsx`
- Create: `packages/guru-web/src/features/documents/DocumentsPage.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { rest } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";

describe("DocumentsPage", () => {
  it("shows list, clicking a row shows detail, metadata pane visible", async () => {
    mockServer.use(
      rest.get("/documents", (_, res, ctx) =>
        res(ctx.json([{ path: "a.md", title: "Alpha", excerpt: "a" }])),
      ),
      rest.get("/documents/a.md", (_, res, ctx) =>
        res(ctx.json({ path: "a.md", title: "Alpha", content: "hello" })),
      ),
      rest.get("/documents/a.md/metadata", (_, res, ctx) =>
        res(ctx.json({ lance: { path: "a.md", chunk_count: 1, token_count: 1, tags: [], ingested_at: null }, graph: null })),
      ),
    );
    renderWithRouter(null, { route: "/documents" });
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByText("Alpha"));
    await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
    expect(screen.getByText("LanceDB")).toBeInTheDocument();
  });

  it("search replaces the list", async () => {
    mockServer.use(
      rest.get("/documents", (_, res, ctx) =>
        res(ctx.json([{ path: "a.md", title: "Alpha", excerpt: "a" }])),
      ),
      rest.post("/documents/search", (_, res, ctx) =>
        res(ctx.json({ hits: [{ path: "b.md", title: "Beta", excerpt: "hit", score: 0.9 }] })),
      ),
    );
    renderWithRouter(null, { route: "/documents" });
    await screen.findByText("Alpha");
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "x" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByText("Beta")).toBeInTheDocument());
    expect(screen.queryByText("Alpha")).toBeNull();
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL.

- [ ] **Step 3: Implement `DocumentsPage`**

```tsx
// DocumentsPage.tsx
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { RightPane } from "../../app/layout/RightPane";
import { useWorkbench } from "../../lib/state/workbench";
import { DocumentDetail } from "./DocumentDetail";
import { DocumentList } from "./DocumentList";
import { DocumentMetaPane } from "./DocumentMetaPane";
import { DocumentSearchBox } from "./DocumentSearchBox";
import type { DocumentSearchHit } from "../../lib/api/hooks";

export function DocumentsPage() {
  const params = useParams();
  const navigate = useNavigate();
  const setSurface = useWorkbench((s) => s.setSurface);
  const boot = useWorkbench((s) => s.boot);
  const selectedPath = params["*"] || null;
  const [hits, setHits] = useState<DocumentSearchHit[] | null>(null);

  useEffect(() => setSurface("documents"), [setSurface]);

  function onSelect(path: string) {
    navigate(`/documents/${path}`);
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <section className="flex w-[320px] flex-col border-r border-neutral-200 bg-white">
        <DocumentSearchBox onResults={setHits} />
        <div className="flex-1 overflow-auto">
          {hits ? (
            <ul className="divide-y divide-neutral-200">
              {hits.map((hit) => (
                <li
                  key={hit.path}
                  aria-selected={hit.path === selectedPath}
                  onClick={() => onSelect(hit.path)}
                  className={
                    "cursor-pointer p-3 text-sm " +
                    (hit.path === selectedPath ? "bg-neutral-900 text-white" : "hover:bg-neutral-100")
                  }
                >
                  <div className="font-medium">{hit.title}</div>
                  <div className="text-xs text-neutral-500">score {hit.score.toFixed(2)} · {hit.excerpt}</div>
                </li>
              ))}
            </ul>
          ) : (
            <DocumentList onSelect={onSelect} selectedPath={selectedPath} />
          )}
        </div>
      </section>
      <section className="flex flex-1 overflow-hidden">
        {selectedPath ? (
          <div className="flex-1 overflow-auto">
            <DocumentDetail path={selectedPath} />
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-neutral-500">
            Select a document to view its content.
          </div>
        )}
        <RightPane>
          {selectedPath ? (
            <DocumentMetaPane path={selectedPath} graphEnabled={boot.graph.enabled} />
          ) : (
            <p className="text-sm text-neutral-500">Select a document to see its metadata.</p>
          )}
        </RightPane>
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd packages/guru-web && npm test -- --run DocumentsPage.test`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/src/features/documents/
git commit -m "feat(web): DocumentsPage three-pane layout with search"
```

---

### Task 4.6: BDD feature `web_documents.feature`

**Files:**
- Create: `tests/e2e/features/web_documents.feature`
- Create: `tests/e2e/features/steps/web_documents_steps.py`

- [ ] **Step 1: Write feature**

```gherkin
# tests/e2e/features/web_documents.feature
@web
Feature: Documents surface

  Background:
    Given a fresh guru project with documents "alpha.md, beta.md, gamma.md"
    And the workbench web UI is available

  Scenario: Full list visible when surface opened
    When I open the Documents surface
    Then I see a document row for "alpha.md"
    And I see a document row for "beta.md"
    And I see a document row for "gamma.md"

  Scenario: Similarity search replaces the list
    When I open the Documents surface
    And I search for "alpha"
    Then the document list shows "alpha.md" ranked first
    And the document list has at most 3 rows

  Scenario: Clicking a document reveals its detail and metadata
    When I open the Documents surface
    And I click the document row for "alpha.md"
    Then I see the document title "alpha.md" in the detail pane
    And the metadata pane shows a "LanceDB" section
    And the metadata pane shows a "Graph" section

  Scenario: Metadata pane is closeable and persists
    When I open the Documents surface
    And I click the document row for "alpha.md"
    And I close the metadata pane
    And I reload the page
    Then the metadata pane is still closed

  Scenario: Go to graph navigates with the doc pre-focused
    When I open the Documents surface
    And I click the document row for "alpha.md"
    And I click "Go to graph"
    Then the URL path is "/graph"
    And the Graph canvas has node "doc:alpha.md" focused
```

- [ ] **Step 2: Write steps**

Add `tests/e2e/features/steps/web_documents_steps.py` with concrete Playwright actions mapping each Gherkin clause. Example:

```python
from behave import given, then, when


@given('the workbench web UI is available')
def step_workbench_available(context):
    assert context.guru.web_runtime_available()


@when('I open the Documents surface')
def step_open_documents(context):
    context.page.goto(f"{context.server_url}/documents")
    context.page.wait_for_load_state("networkidle")


@then('I see a document row for "{name}"')
def step_see_row(context, name):
    assert context.page.get_by_role("listitem", name=name).is_visible()


@when('I search for "{query}"')
def step_search(context, query):
    box = context.page.get_by_placeholder("Search documents (similarity)")
    box.fill(query)
    box.press("Enter")


@then('the document list shows "{name}" ranked first')
def step_ranked(context, name):
    first = context.page.get_by_role("listitem").first
    first.wait_for()
    assert name in first.inner_text()


@then('the document list has at most {n:d} rows')
def step_row_count(context, n):
    assert context.page.get_by_role("listitem").count() <= n


@when('I click the document row for "{name}"')
def step_click_doc(context, name):
    context.page.get_by_role("listitem", name=name).click()


@then('I see the document title "{title}" in the detail pane')
def step_title(context, title):
    assert context.page.get_by_role("heading", name=title).is_visible()


@then('the metadata pane shows a "{label}" section')
def step_meta_section(context, label):
    assert context.page.get_by_text(label).is_visible()


@when('I close the metadata pane')
def step_close_meta(context):
    context.page.get_by_role("button", name="Toggle metadata pane").click()


@when('I reload the page')
def step_reload(context):
    context.page.reload()


@then('the metadata pane is still closed')
def step_pane_closed(context):
    assert not context.page.get_by_text("LanceDB").is_visible()


@when('I click "Go to graph"')
def step_click_go_to_graph(context):
    context.page.get_by_role("button", name="Go to graph").click()


@then('the URL path is "{path}"')
def step_url_path(context, path):
    assert context.page.url.endswith(path) or f"{path}?" in context.page.url


@then('the Graph canvas has node "{node_id}" focused')
def step_graph_focused(context, node_id):
    assert context.page.locator(f'[data-node-id="{node_id}"][data-focused="true"]').is_visible()
```

- [ ] **Step 3: Run the feature**

```bash
uv run behave tests/e2e/features/web_documents.feature -t @web
```

Expected: 5 scenarios pass.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/features/web_documents.feature tests/e2e/features/steps/web_documents_steps.py
git commit -m "test(e2e): BDD for Documents surface"
```

---

## Phase 5 — Graph surface

### Task 5.1: Initial canvas renders federation root + KBs via `GET /graph/roots`

**Files:**
- Modify: `packages/guru-web/src/features/graph/GraphPage.tsx`
- Modify: `packages/guru-web/src/features/graph/mapGraph.ts`
- Create: `packages/guru-web/src/features/graph/useGraphRoots.ts`
- Test: `packages/guru-web/src/features/graph/useGraphRoots.test.ts`

- [ ] **Step 1: Write failing test**

```ts
// useGraphRoots.test.ts
import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { rest } from "msw";

import { mockServer } from "../../test/msw";
import { useGraphRoots } from "./useGraphRoots";
import { wrapperWithQueryClient } from "../../test/render";

describe("useGraphRoots", () => {
  it("returns federation_root + kbs", async () => {
    mockServer.use(
      rest.get("/graph/roots", (_, res, ctx) =>
        res(ctx.json({
          federation_root: { id: "federation", label: "Federation" },
          kbs: [{ name: "local", project_root: "/p", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", last_seen_at: null, tags: [], metadata: {} }],
        })),
      ),
    );
    const { result } = renderHook(() => useGraphRoots(), { wrapper: wrapperWithQueryClient });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data!.federation_root.id).toBe("federation");
    expect(result.current.data!.kbs[0].name).toBe("local");
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL (hook missing).

- [ ] **Step 3: Implement hook + use it in `GraphPage`**

```ts
// useGraphRoots.ts
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../../lib/api/client";

export interface Kb {
  name: string;
  project_root: string;
  tags: string[];
}
export interface GraphRoots {
  federation_root: { id: "federation"; label: string };
  kbs: Kb[];
}

export function useGraphRoots() {
  return useQuery<GraphRoots>({
    queryKey: ["graph", "roots"],
    queryFn: async () => apiClient.get<GraphRoots>("/graph/roots"),
  });
}
```

Update `mapGraph.ts` to accept an initial skeleton `{ federation_root, kbs }` and produce ReactFlow node/edge shapes. The federation root is a special pinned node at position (0,0); each KB fans out in a ring.

```ts
// mapGraph.ts (additive)
import type { Node, Edge } from "reactflow";

export interface GraphRoots {
  federation_root: { id: "federation"; label: string };
  kbs: { name: string }[];
}

export function rootsToFlow(roots: GraphRoots): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [
    {
      id: "federation",
      data: { label: roots.federation_root.label, kind: "federation" },
      position: { x: 0, y: 0 },
      type: "default",
      draggable: false,
    },
  ];
  const edges: Edge[] = [];
  const ringRadius = 240;
  roots.kbs.forEach((kb, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, roots.kbs.length);
    nodes.push({
      id: `kb:${kb.name}`,
      data: { label: kb.name, kind: "kb" },
      position: { x: ringRadius * Math.cos(angle), y: ringRadius * Math.sin(angle) },
      type: "default",
      draggable: false,
    });
    edges.push({ id: `federation->kb:${kb.name}`, source: "federation", target: `kb:${kb.name}`, style: { strokeDasharray: "4 4", opacity: 0.6 } });
  });
  return { nodes, edges };
}
```

Rewrite the top of `GraphPage.tsx` to render `rootsToFlow(roots.data)` on first load.

- [ ] **Step 4: Add component test**

```tsx
// GraphPage.test.tsx (rewrite)
it("renders federation root + each KB on initial load", async () => {
  mockServer.use(
    rest.get("/graph/roots", (_, res, ctx) =>
      res(ctx.json({
        federation_root: { id: "federation", label: "Federation" },
        kbs: [{ name: "local", project_root: "/p", tags: [] }, { name: "peer", project_root: "/q", tags: [] }],
      })),
    ),
  );
  renderWithRouter(null, { route: "/graph" });
  await screen.findByText("Federation");
  expect(screen.getByText("local")).toBeInTheDocument();
  expect(screen.getByText("peer")).toBeInTheDocument();
});
```

- [ ] **Step 5: Run**

Run: `cd packages/guru-web && npm test -- --run useGraphRoots.test GraphPage.test`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web/src/features/graph/
git commit -m "feat(web): graph canvas renders federation root + KB nodes"
```

---

### Task 5.2: Incremental expand on node click

**Files:**
- Modify: `packages/guru-web/src/features/graph/GraphPage.tsx`
- Create: `packages/guru-web/src/features/graph/useGraphCanvas.ts`
- Test: `packages/guru-web/src/features/graph/useGraphCanvas.test.ts`

- [ ] **Step 1: Write failing test**

```ts
// useGraphCanvas.test.ts
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useGraphCanvas } from "./useGraphCanvas";
import { wrapperWithQueryClient } from "../../test/render";

const rootsPayload = {
  federation_root: { id: "federation", label: "Federation" },
  kbs: [{ name: "local", project_root: "/p", tags: [] }],
};

describe("useGraphCanvas", () => {
  it("starts with roots only", () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    const ids = result.current.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["federation", "kb:local"]);
  });

  it("merges neighbors without duplicating existing nodes", async () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    await act(async () => {
      result.current.mergeNeighbors("doc:a.md", {
        nodes: [
          { id: "doc:a.md", label: "A", kind: "document", kb: "local" },
          { id: "kb:local", label: "local", kind: "kb" },
          { id: "doc:b.md", label: "B", kind: "document", kb: "local" },
        ],
        edges: [{ source: "doc:a.md", target: "doc:b.md", kind: "RELATED" }],
      });
    });
    const ids = result.current.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["doc:a.md", "doc:b.md", "federation", "kb:local"]);
  });

  it("clear resets to roots only", async () => {
    const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
    await act(async () => {
      result.current.mergeNeighbors("doc:a.md", {
        nodes: [{ id: "doc:a.md", label: "A", kind: "document", kb: "local" }],
        edges: [],
      });
      result.current.clear();
    });
    const ids = result.current.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["federation", "kb:local"]);
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL (hook missing).

- [ ] **Step 3: Implement `useGraphCanvas`**

```ts
// useGraphCanvas.ts
import { useCallback, useMemo, useState } from "react";
import type { Edge, Node } from "reactflow";

import { rootsToFlow, GraphRoots } from "./mapGraph";

interface NeighborsPayload {
  nodes: { id: string; label: string; kind: string; kb?: string }[];
  edges: { source: string; target: string; kind: string }[];
}

export function useGraphCanvas(roots: GraphRoots | undefined) {
  const rootsFlow = useMemo(() => (roots ? rootsToFlow(roots) : { nodes: [], edges: [] }), [roots]);
  const [extraNodes, setExtraNodes] = useState<Node[]>([]);
  const [extraEdges, setExtraEdges] = useState<Edge[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const mergeNeighbors = useCallback((focusId: string, payload: NeighborsPayload) => {
    setExtraNodes((prev) => {
      const existing = new Set(prev.map((n) => n.id).concat(rootsFlow.nodes.map((n) => n.id)));
      const additions: Node[] = [];
      payload.nodes.forEach((n, i) => {
        if (existing.has(n.id)) return;
        additions.push({
          id: n.id,
          data: { label: n.label, kind: n.kind, kb: n.kb },
          position: { x: 400 + 120 * Math.cos(i), y: 120 * Math.sin(i) },
          type: "default",
        });
      });
      return [...prev, ...additions];
    });
    setExtraEdges((prev) => {
      const existing = new Set(prev.map((e) => `${e.source}->${e.target}`));
      const additions: Edge[] = payload.edges
        .filter((e) => !existing.has(`${e.source}->${e.target}`))
        .map((e) => ({ id: `${e.source}->${e.target}`, source: e.source, target: e.target, label: e.kind }));
      return [...prev, ...additions];
    });
    setSelectedId(focusId);
  }, [rootsFlow.nodes]);

  const clear = useCallback(() => {
    setExtraNodes([]);
    setExtraEdges([]);
    setSelectedId(null);
  }, []);

  return {
    nodes: [...rootsFlow.nodes, ...extraNodes],
    edges: [...rootsFlow.edges, ...extraEdges],
    selectedId,
    setSelectedId,
    mergeNeighbors,
    clear,
  };
}
```

- [ ] **Step 4: Wire into `GraphPage`**

Call `mergeNeighbors(clickedId, payload)` whenever a node is clicked. Use the existing `getGraphNeighbors` API call (or add `apiClient.get<{nodes, edges}>("/graph/neighbors/<id>")`).

- [ ] **Step 5: Run tests**

Run: `cd packages/guru-web && npm test -- --run useGraphCanvas.test`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web/src/features/graph/
git commit -m "feat(web): incremental graph expansion on node click"
```

---

### Task 5.3: Path-to-root overlay

**Files:**
- Create: `packages/guru-web/src/features/graph/computePathToRoot.ts`
- Create: `packages/guru-web/src/features/graph/computePathToRoot.test.ts`
- Modify: `packages/guru-web/src/features/graph/GraphPage.tsx`

- [ ] **Step 1: Write failing test**

```ts
import { describe, expect, it } from "vitest";
import { computePathToRoot } from "./computePathToRoot";

describe("computePathToRoot", () => {
  it("returns [] when selection is the federation root", () => {
    expect(computePathToRoot("federation", "local")).toEqual([]);
  });

  it("returns [federation -> kb] when selection is a KB node", () => {
    expect(computePathToRoot("kb:local", "local")).toEqual([
      { source: "federation", target: "kb:local" },
    ]);
  });

  it("returns [federation -> kb -> doc] when selection is a document", () => {
    expect(computePathToRoot("doc:a.md", "local")).toEqual([
      { source: "federation", target: "kb:local" },
      { source: "kb:local", target: "doc:a.md" },
    ]);
  });

  it("returns [] when selection is null", () => {
    expect(computePathToRoot(null, "local")).toEqual([]);
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// computePathToRoot.ts
export interface OverlayEdge { source: string; target: string }

export function computePathToRoot(selectedId: string | null, localKbName: string): OverlayEdge[] {
  if (!selectedId || selectedId === "federation") return [];
  const kbId = `kb:${localKbName}`;
  if (selectedId === kbId) return [{ source: "federation", target: kbId }];
  return [
    { source: "federation", target: kbId },
    { source: kbId, target: selectedId },
  ];
}
```

- [ ] **Step 4: Render overlay in `GraphPage`**

In `GraphPage.tsx`, compute overlay edges from `selectedId` and the local KB name (from boot payload), and append them to the edges array given to ReactFlow. Tag overlay edges with `data: { kind: "hierarchy" }` and a class; apply a dashed style and distinct color via an edge class resolver:

```tsx
const overlayEdges = computePathToRoot(selectedId, boot.kb_name || "local").map((e) => ({
  id: `overlay:${e.source}->${e.target}`,
  source: e.source,
  target: e.target,
  type: "straight",
  animated: true,
  style: { strokeDasharray: "6 4", stroke: "#a855f7" },
  label: "hierarchy",
}));
```

- [ ] **Step 5: Run tests**

Run: `cd packages/guru-web && npm test -- --run computePathToRoot.test`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web/src/features/graph/
git commit -m "feat(web): dashed path-to-root overlay following selection"
```

---

### Task 5.4: Cypher query input + replace projection

**Files:**
- Create: `packages/guru-web/src/features/graph/QueryInput.tsx`
- Create: `packages/guru-web/src/features/graph/QueryInput.test.tsx`
- Modify: `packages/guru-web/src/features/graph/GraphPage.tsx`
- Modify: `packages/guru-web/src/lib/api/hooks.ts` (add `runGraphQuery`)

- [ ] **Step 1: Write failing test**

```tsx
import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";

import { renderWithRouter } from "../../test/render";
import { QueryInput } from "./QueryInput";

describe("QueryInput", () => {
  it("calls onRun with the cypher text when submitted", () => {
    const onRun = vi.fn();
    renderWithRouter(<QueryInput onRun={onRun} />);
    fireEvent.change(screen.getByLabelText(/cypher/i), { target: { value: "MATCH (n) RETURN n" } });
    fireEvent.click(screen.getByRole("button", { name: /run/i }));
    expect(onRun).toHaveBeenCalledWith("MATCH (n) RETURN n");
  });

  it("calls onRestore when Back to exploration clicked", () => {
    const onRestore = vi.fn();
    renderWithRouter(<QueryInput onRun={() => {}} onRestore={onRestore} inResultsMode />);
    fireEvent.click(screen.getByRole("button", { name: /back to exploration/i }));
    expect(onRestore).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL (no component).

- [ ] **Step 3: Implement `QueryInput`**

```tsx
// QueryInput.tsx
import { useState } from "react";

export function QueryInput({
  onRun,
  onRestore,
  inResultsMode,
}: {
  onRun: (cypher: string) => void;
  onRestore?: () => void;
  inResultsMode?: boolean;
}) {
  const [text, setText] = useState("");
  return (
    <div className="flex items-center gap-2 border-b border-neutral-200 bg-white p-2">
      <label htmlFor="cypher" className="sr-only">Cypher</label>
      <input
        id="cypher"
        className="flex-1 rounded border border-neutral-300 px-2 py-1 font-mono text-xs"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Cypher (read-only)"
      />
      <button type="button" onClick={() => onRun(text)} className="rounded bg-neutral-900 px-2 py-1 text-xs text-white">
        Run
      </button>
      {inResultsMode && onRestore ? (
        <button type="button" onClick={onRestore} className="rounded border border-neutral-300 px-2 py-1 text-xs">
          Back to exploration
        </button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Add `runGraphQuery`**

```ts
// hooks.ts
export interface GraphQueryResult {
  nodes: { id: string; label: string; kind: string; kb?: string }[];
  edges: { source: string; target: string; kind: string }[];
}

export async function runGraphQuery(cypher: string): Promise<GraphQueryResult> {
  return apiClient.post<GraphQueryResult>("/graph/query", { cypher });
}
```

- [ ] **Step 5: Wire projection into `GraphPage`**

In `GraphPage`:

```tsx
const [resultsMode, setResultsMode] = useState<{ prev: {nodes: Node[]; edges: Edge[]} | null } | null>(null);

async function onRunQuery(cypher: string) {
  const prev = { nodes: canvas.nodes, edges: canvas.edges };
  const result = await runGraphQuery(cypher);
  // keep roots pinned
  canvas.replaceProjection(result);
  setResultsMode({ prev });
}

function onRestore() {
  if (resultsMode?.prev) canvas.restore(resultsMode.prev);
  setResultsMode(null);
}
```

Add `replaceProjection` and `restore` to `useGraphCanvas`:

```ts
// useGraphCanvas.ts additions
const replaceProjection = useCallback((payload: NeighborsPayload) => {
  setExtraNodes(payload.nodes
    .filter(n => n.id !== "federation" && !n.id.startsWith("kb:"))
    .map((n, i) => ({
      id: n.id,
      data: { label: n.label, kind: n.kind, kb: n.kb },
      position: { x: 400 + 120 * Math.cos(i), y: 120 * Math.sin(i) },
      type: "default",
    })));
  setExtraEdges(payload.edges.map((e) => ({ id: `q:${e.source}->${e.target}`, source: e.source, target: e.target, label: e.kind })));
}, []);

const restore = useCallback((snapshot: {nodes: Node[]; edges: Edge[]}) => {
  const isRoot = (id: string) => id === "federation" || id.startsWith("kb:");
  setExtraNodes(snapshot.nodes.filter((n) => !isRoot(n.id)));
  setExtraEdges(snapshot.edges.filter((e) => !isRoot(e.source) && !isRoot(e.target)));
}, []);
```

Add tests for both methods in `useGraphCanvas.test.ts`:

```ts
it("replaceProjection keeps roots and swaps extras", async () => {
  const { result } = renderHook(() => useGraphCanvas(rootsPayload), { wrapper: wrapperWithQueryClient });
  await act(async () => {
    result.current.replaceProjection({
      nodes: [{ id: "doc:x", label: "X", kind: "document", kb: "local" }, { id: "federation", label: "F", kind: "federation" }],
      edges: [],
    });
  });
  expect(result.current.nodes.map((n) => n.id).sort()).toEqual(["doc:x", "federation", "kb:local"]);
});
```

- [ ] **Step 6: Run tests**

Run: `cd packages/guru-web && npm test -- --run QueryInput.test useGraphCanvas.test`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/guru-web/src/features/graph/ packages/guru-web/src/lib/api/hooks.ts
git commit -m "feat(web): Cypher input with replace-canvas projection + restore"
```

---

### Task 5.5: Graph metadata pane

**Files:**
- Create: `packages/guru-web/src/features/graph/GraphMetaPane.tsx`
- Create: `packages/guru-web/src/features/graph/GraphMetaPane.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// GraphMetaPane.test.tsx
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { rest } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { GraphMetaPane } from "./GraphMetaPane";

describe("GraphMetaPane", () => {
  it("shows metadata for a selected document node", async () => {
    mockServer.use(
      rest.get("/documents/a.md/metadata", (_, res, ctx) =>
        res(ctx.json({
          lance: { path: "a.md", chunk_count: 1, token_count: 1, tags: [], ingested_at: null },
          graph: { node_id: "doc:a.md", degree: 3, links: [] },
        })),
      ),
    );
    renderWithRouter(<GraphMetaPane selectedId="doc:a.md" />);
    expect(await screen.findByText("LanceDB")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders empty state for federation root", () => {
    renderWithRouter(<GraphMetaPane selectedId="federation" />);
    expect(screen.getByText(/orientation anchor/i)).toBeInTheDocument();
  });

  it("renders KB summary for kb: node", () => {
    renderWithRouter(<GraphMetaPane selectedId="kb:local" />);
    expect(screen.getByText(/knowledge base/i)).toBeInTheDocument();
    expect(screen.getByText("local")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL.

- [ ] **Step 3: Implement**

```tsx
// GraphMetaPane.tsx
import { DocumentMetaPane } from "../documents/DocumentMetaPane";

export function GraphMetaPane({ selectedId }: { selectedId: string | null }) {
  if (!selectedId) return <p className="text-sm text-neutral-500">Select a node to see its metadata.</p>;
  if (selectedId === "federation") return <p className="text-sm text-neutral-500">The Federation root is a UI-only orientation anchor.</p>;
  if (selectedId.startsWith("kb:")) {
    const name = selectedId.slice(3);
    return (
      <div className="space-y-2 text-sm">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">Knowledge base</h3>
        <div>{name}</div>
      </div>
    );
  }
  if (selectedId.startsWith("doc:")) {
    const path = selectedId.slice(4);
    return <DocumentMetaPane path={path} graphEnabled={true} />;
  }
  return <p className="text-sm text-neutral-500">Unsupported node.</p>;
}
```

- [ ] **Step 4: Run tests**

Run: `cd packages/guru-web && npm test -- --run GraphMetaPane.test`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/src/features/graph/GraphMetaPane.tsx packages/guru-web/src/features/graph/GraphMetaPane.test.tsx
git commit -m "feat(web): GraphMetaPane surfacing LanceDB + graph meta"
```

---

### Task 5.6: Integrate all of Phase 5 in `GraphPage.tsx`

**Files:**
- Modify: `packages/guru-web/src/features/graph/GraphPage.tsx`
- Modify: `packages/guru-web/src/features/graph/GraphPage.test.tsx`

- [ ] **Step 1: Rewrite `GraphPage`**

```tsx
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { RightPane } from "../../app/layout/RightPane";
import { useWorkbench } from "../../lib/state/workbench";
import { apiClient } from "../../lib/api/client";
import { runGraphQuery } from "../../lib/api/hooks";
import { GraphMetaPane } from "./GraphMetaPane";
import { QueryInput } from "./QueryInput";
import { computePathToRoot } from "./computePathToRoot";
import { useGraphCanvas } from "./useGraphCanvas";
import { useGraphRoots } from "./useGraphRoots";

export function GraphPage() {
  const roots = useGraphRoots();
  const canvas = useGraphCanvas(roots.data);
  const boot = useWorkbench((s) => s.boot);
  const setSurface = useWorkbench((s) => s.setSurface);
  const [params] = useSearchParams();
  const focus = params.get("focus");
  const [resultsMode, setResultsMode] = useState<{ prev: { nodes: any[]; edges: any[] } } | null>(null);

  useEffect(() => setSurface("graph"), [setSurface]);

  useEffect(() => {
    if (!focus || !roots.data) return;
    (async () => {
      const payload = await apiClient.get<any>(`/graph/neighbors/${encodeURIComponent(focus)}`);
      canvas.mergeNeighbors(focus, payload);
    })();
  }, [focus, roots.data]);

  const overlayEdges = computePathToRoot(canvas.selectedId, (boot as any).kb_name || "local").map((e) => ({
    id: `overlay:${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    style: { strokeDasharray: "6 4", stroke: "#a855f7" },
    animated: true,
  }));

  async function onRunQuery(cypher: string) {
    const prev = { nodes: canvas.nodes, edges: canvas.edges };
    const result = await runGraphQuery(cypher);
    canvas.replaceProjection(result);
    setResultsMode({ prev });
  }

  async function onNodeClick(_: unknown, node: { id: string }) {
    canvas.setSelectedId(node.id);
    if (node.id === "federation" || node.id.startsWith("kb:")) return;
    const payload = await apiClient.get<any>(`/graph/neighbors/${encodeURIComponent(node.id)}`);
    canvas.mergeNeighbors(node.id, payload);
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex flex-1 flex-col">
        <QueryInput onRun={onRunQuery} onRestore={() => {
          if (resultsMode?.prev) canvas.restore(resultsMode.prev);
          setResultsMode(null);
        }} inResultsMode={!!resultsMode} />
        <div className="flex flex-1">
          <ReactFlow
            nodes={canvas.nodes}
            edges={[...canvas.edges, ...overlayEdges]}
            onNodeClick={onNodeClick}
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>
      </div>
      <RightPane>
        <GraphMetaPane selectedId={canvas.selectedId} />
      </RightPane>
    </div>
  );
}
```

- [ ] **Step 2: Add integration test**

```tsx
// GraphPage.test.tsx additions
it("focuses via ?focus= and draws path-to-root", async () => {
  mockServer.use(
    rest.get("/graph/roots", (_, res, ctx) => res(ctx.json({ federation_root: { id: "federation", label: "F" }, kbs: [{ name: "local", project_root: "/p", tags: [] }] }))),
    rest.get("/graph/neighbors/doc%3Aa.md", (_, res, ctx) => res(ctx.json({ nodes: [{ id: "doc:a.md", label: "A", kind: "document", kb: "local" }], edges: [] }))),
  );
  renderWithRouter(null, { route: "/graph?focus=doc%3Aa.md" });
  await screen.findByText("A");
  const overlayPurple = document.querySelectorAll('[stroke="#a855f7"]');
  expect(overlayPurple.length).toBeGreaterThan(0);
});
```

- [ ] **Step 3: Run tests**

Run: `cd packages/guru-web && npm test -- --run GraphPage.test`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/guru-web/src/features/graph/GraphPage.tsx packages/guru-web/src/features/graph/GraphPage.test.tsx
git commit -m "feat(web): wire GraphPage with expand+query+path overlay+meta"
```

---

### Task 5.7: BDD feature `web_graph.feature`

**Files:**
- Create: `tests/e2e/features/web_graph.feature`
- Create: `tests/e2e/features/steps/web_graph_steps.py`

- [ ] **Step 1: Write feature**

```gherkin
@web
Feature: Graph surface

  Background:
    Given a fresh guru project with documents "a.md, b.md"
    And the graph daemon is enabled
    And the workbench web UI is available

  Scenario: Initial canvas shows federation root and the local KB
    When I open the Graph surface
    Then the canvas has node "federation"
    And the canvas has node "kb:local"
    And the canvas has 2 nodes

  Scenario: Clicking a KB node reveals its document children
    When I open the Graph surface
    And I click the canvas node "kb:local"
    Then the canvas has node "doc:a.md"
    And the canvas has node "doc:b.md"

  Scenario: Clicking a document node merges its neighbors
    Given documents "a.md" and "b.md" are linked in the graph
    When I open the Graph surface
    And I click the canvas node "kb:local"
    And I click the canvas node "doc:a.md"
    Then the canvas has node "doc:b.md"
    And a path-to-root overlay connects "federation" to "kb:local" to "doc:a.md"

  Scenario: Clear returns to root + KB only
    When I open the Graph surface
    And I click the canvas node "kb:local"
    And I click the canvas Clear button
    Then the canvas has 2 nodes

  Scenario: Cypher projection replaces the canvas
    When I open the Graph surface
    And I run the Cypher query "MATCH (d:Document {path:'a.md'}) RETURN d"
    Then the canvas has node "doc:a.md"
    And the canvas does not have node "doc:b.md"
    And the canvas has node "federation"

  Scenario: Back to exploration restores prior state
    When I open the Graph surface
    And I click the canvas node "kb:local"
    And I run the Cypher query "MATCH (d:Document {path:'a.md'}) RETURN d"
    And I click "Back to exploration"
    Then the canvas has node "doc:b.md"

  Scenario: Write cypher is rejected
    When I open the Graph surface
    And I run the Cypher query "CREATE (:Document {id:'x.md'})"
    Then the Cypher input shows the error "writes are not permitted"

  Scenario: Graph disabled shows a banner, not a canvas
    Given the graph daemon is disabled
    When I open the Graph surface
    Then I see the banner "Graph daemon is disabled"
```

- [ ] **Step 2: Write steps**

Create `tests/e2e/features/steps/web_graph_steps.py` with Playwright-driven step definitions analogous to `web_documents_steps.py`. Assert canvas structure via `data-node-id` attributes on ReactFlow nodes (add `nodeDataAttributes` to the ReactFlow setup if not already present).

- [ ] **Step 3: Run the feature**

```bash
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/web_graph.feature -t @web
```

Expected: 8 scenarios pass.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/features/web_graph.feature tests/e2e/features/steps/web_graph_steps.py
git commit -m "test(e2e): BDD for Graph surface"
```

---

## Phase 6 — Status surface

### Task 6.1: `StatusPage` with sync status + reconcile button

**Files:**
- Modify: `packages/guru-web/src/features/status/StatusPage.tsx`
- Create: `packages/guru-web/src/features/status/StatusPage.test.tsx`
- Modify: `packages/guru-web/src/lib/api/hooks.ts` (add `useSyncStatus`, `reconcileSync`)

- [ ] **Step 1: Write failing test**

```tsx
// StatusPage.test.tsx
import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { rest } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";

describe("StatusPage", () => {
  it("renders sync counts and reconcile button", async () => {
    mockServer.use(
      rest.get("/sync/status", (_, res, ctx) =>
        res(ctx.json({ lancedb_count: 5, graph_count: 4, drift: 1, last_reconciled_at: null, graph_enabled: true })),
      ),
    );
    renderWithRouter(null, { route: "/status" });
    await screen.findByText("LanceDB documents");
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("drift")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reconcile now/i })).toBeInTheDocument();
  });

  it("triggers reconcile and updates counts", async () => {
    let phase = 0;
    mockServer.use(
      rest.get("/sync/status", (_, res, ctx) => {
        phase++;
        return res(ctx.json({
          lancedb_count: 5, graph_count: phase === 1 ? 4 : 5, drift: phase === 1 ? 1 : 0,
          last_reconciled_at: null, graph_enabled: true,
        }));
      }),
      rest.post("/sync/reconcile", (_, res, ctx) =>
        res(ctx.json({ lancedb_count: 5, graph_count: 5, drift: 0, last_reconciled_at: "now", graph_enabled: true })),
      ),
    );
    renderWithRouter(null, { route: "/status" });
    await screen.findByText("1");
    fireEvent.click(screen.getByRole("button", { name: /reconcile now/i }));
    await waitFor(() => expect(screen.getByText("0")).toBeInTheDocument());
  });

  it("disables reconcile button when graph disabled", async () => {
    mockServer.use(
      rest.get("/sync/status", (_, res, ctx) =>
        res(ctx.json({ lancedb_count: 5, graph_count: 0, drift: 5, last_reconciled_at: null, graph_enabled: false })),
      ),
    );
    renderWithRouter(null, { route: "/status" });
    const btn = await screen.findByRole("button", { name: /reconcile now/i });
    expect(btn).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run — should fail**

Expected: FAIL (page is a stub).

- [ ] **Step 3: Add hook + implementation**

```ts
// hooks.ts additions
export interface SyncStatus {
  lancedb_count: number;
  graph_count: number;
  drift: number;
  last_reconciled_at: string | null;
  graph_enabled: boolean;
}

export function useSyncStatus() {
  return useQuery<SyncStatus>({
    queryKey: ["sync", "status"],
    queryFn: async () => apiClient.get<SyncStatus>("/sync/status"),
    refetchInterval: 10_000,
  });
}

export async function reconcileSync(): Promise<SyncStatus> {
  return apiClient.post<SyncStatus>("/sync/reconcile", {});
}
```

```tsx
// StatusPage.tsx
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useWorkbench } from "../../lib/state/workbench";
import { reconcileSync, useSyncStatus } from "../../lib/api/hooks";

export function StatusPage() {
  const boot = useWorkbench((s) => s.boot);
  const { data, isLoading } = useSyncStatus();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  async function reconcile() {
    setBusy(true);
    try {
      const next = await reconcileSync();
      qc.setQueryData(["sync", "status"], next);
    } finally {
      setBusy(false);
    }
  }

  if (isLoading || !data) return <div className="p-6 text-sm text-neutral-500">Loading…</div>;

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="text-xl font-semibold">Status</h1>
      <section className="mt-6 grid max-w-3xl grid-cols-3 gap-4">
        <Card title="LanceDB documents" value={data.lancedb_count} />
        <Card title="Graph documents" value={data.graph_count} />
        <Card title="drift" value={data.drift} />
      </section>
      <section className="mt-6 max-w-3xl rounded border border-neutral-200 bg-white p-4 text-sm">
        <div>Project: <strong>{boot.project.name}</strong></div>
        <div>Graph daemon: <strong>{data.graph_enabled ? "enabled" : "disabled"}</strong></div>
        <div>Last reconciled: <strong>{data.last_reconciled_at ?? "—"}</strong></div>
        <button
          type="button"
          onClick={reconcile}
          disabled={!data.graph_enabled || busy}
          className="mt-4 rounded bg-neutral-900 px-3 py-1 text-white disabled:opacity-50"
        >
          Reconcile now
        </button>
      </section>
    </div>
  );
}

function Card({ title, value }: { title: string; value: number }) {
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500">{title}</div>
      <div className="mt-1 text-3xl font-semibold">{value}</div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd packages/guru-web && npm test -- --run StatusPage.test`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/src/features/status/ packages/guru-web/src/lib/api/hooks.ts
git commit -m "feat(web): StatusPage with sync counts and reconcile"
```

---

### Task 6.2: BDD feature `web_status.feature`

**Files:**
- Create: `tests/e2e/features/web_status.feature`
- Create: `tests/e2e/features/steps/web_status_steps.py`

- [ ] **Step 1: Write feature**

```gherkin
@web
Feature: Status surface

  Background:
    Given a fresh guru project with documents "a.md, b.md"
    And the workbench web UI is available

  Scenario: Healthy graph shows 0 drift
    Given the graph daemon is enabled
    When I open the Status surface
    Then I see the drift value "0"

  Scenario: Disabled graph disables reconcile
    Given the graph daemon is disabled
    When I open the Status surface
    Then the "Reconcile now" button is disabled

  Scenario: Reconcile heals drift
    Given the graph store is pruned
    When I open the Status surface
    Then I see the drift value "2"
    When I click "Reconcile now"
    Then I see the drift value "0"
```

- [ ] **Step 2: Write steps**

Create `tests/e2e/features/steps/web_status_steps.py` with the analogous Playwright steps.

- [ ] **Step 3: Run**

```bash
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/web_status.feature -t @web
```

Expected: 3 scenarios pass.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/features/web_status.feature tests/e2e/features/steps/web_status_steps.py
git commit -m "test(e2e): BDD for Status surface"
```

---

## Phase 7 — Cleanup + invariants

### Task 7.1: Purge remaining "artifact" references in the web UI

**Files:**
- Sweep: `packages/guru-web/src/`
- Modify: any lingering component strings, comments, type names.

- [ ] **Step 1: Search for "artifact" in the web package**

Run: `grep -rniE "artifact|workbenchEntit|investigateResults|graph plan" packages/guru-web/src`
Expected: only test fixtures or comments explicitly documenting removal. Every functional reference must be gone.

- [ ] **Step 2: Rename leftovers**

Replace every leftover use of `artifact` in UI code with `document` (state shapes, comments, IDs). Exceptions:
- `packages/guru-core/src/guru_core/graph_types.py` — may keep `ArtifactNode` if it exists (it's a backend-only concept).
- `tests/e2e/features/artifact_indexing.feature` and `tests/e2e/features/artifact_links.feature` stay untouched; they test non-UI graph behavior.

- [ ] **Step 3: Re-run the web test suite**

Run: `cd packages/guru-web && npm test -- --run`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/guru-web/src/
git commit -m "refactor(web): rename remaining 'artifact' references to 'document'"
```

---

### Task 7.2: ARCHITECTURE.md invariant addendum

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Add the three invariants from the spec**

Append (or insert under the relevant "Invariants" section):

```markdown
## Web UI invariants

- The web UI never surfaces non-document graph nodes. All graph payloads
  consumed by `guru-web` are filtered server-side to document-kind nodes.
- LanceDB is the authoritative source of document identity. The graph stores
  document-kind nodes only as a mirror. Sync conflicts are resolved in
  LanceDB's favor.
- The federation root is UI-only. It is never stored in the graph and must
  not appear in graph query results.
```

- [ ] **Step 2: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs(arch): web UI invariants for sync + federation-root"
```

---

### Task 7.3: Update USAGE.md if present

**Files:**
- Possibly: `USAGE.md`

- [ ] **Step 1: Check whether USAGE.md references the old surfaces**

Run: `grep -niE "investigate|operate|workbench.*query|artifact" USAGE.md`
Expected: some matches.

- [ ] **Step 2: Replace sections**

Update the "Workbench" / "Web UI" section of `USAGE.md` to reflect the three surfaces (Documents, Graph, Status), the search-based doc flow, the graph expansion model, and the reconcile action.

Where `USAGE.md` is generated by `curate-usage-md`, trigger a regen instead of editing by hand:

```bash
# Per CLAUDE.md instructions — the skill regenerates USAGE.md.
```

- [ ] **Step 3: Commit**

```bash
git add USAGE.md
git commit -m "docs(usage): update web UI section for documents/graph/status"
```

---

### Task 7.4: Full test sweep + build

**Files:** none.

- [ ] **Step 1: Run the full suite**

```bash
make lint
make test
make test-all       # includes e2e; may need GURU_REAL_NEO4J=1 + start-test-neo4j.sh
make build          # ensure all 5 wheels still build
cd packages/guru-web && npm run build
```

Expected: every target PASS.

- [ ] **Step 2: Commit and push only if something still needs fixing**

If any step fails, fix and add a commit; do not commit speculative changes.

---

## Self-review checklist

1. **Spec coverage**

   | Spec section | Task(s) |
   |---|---|
   | Scope & vocabulary: remove "artifact" | 3.1, 3.2, 7.1 |
   | Remove workbenchEntities mock | 3.1 |
   | Filter code-extracted nodes out of web | 2.3 |
   | Sync invariant (SyncService + triggers) | 1.1, 1.2, 1.3, 1.5, 1.6 |
   | Backfill on graph enable | 1.1 + 1.5 (startup reconcile handles this) |
   | Delete propagation | 1.6 |
   | /sync/status, /sync/reconcile | 1.7 |
   | Three surfaces, top menu bar, closeable pane | 3.2 |
   | Documents: list, search, detail, meta, Go to graph | 4.1–4.5 |
   | POST /documents/search | 2.1 |
   | Graph: federation root + KBs on load | 2.2, 5.1 |
   | Graph: incremental expand | 5.2 |
   | Graph: path-to-root overlay | 5.3 |
   | Graph: Cypher projection replace + restore | 2.4, 5.4 |
   | Graph metadata pane | 5.5 |
   | Status surface + reconcile button | 6.1 |
   | BDD features | 1.8, 4.6, 5.7, 6.2 |
   | Playwright dev dep | 0.2 |
   | ARCHITECTURE.md invariants | 7.2 |
   | USAGE.md refresh | 7.3 |

2. **Placeholder scan** — no "TBD", "TODO" outside explicit temporary commented-out imports in Task 3.1 Step 5 (which are removed in 3.2 Step 6). Every step has concrete code or concrete commands.

3. **Type consistency** — `SyncService.status()` and `SyncService.reconcile()` both return `SyncStatus`. `SyncService.upsert_one`, `delete_one`, and `graph_enabled` are declared in Task 1.6 Step 4 and used in Task 1.6 Step 5 and Task 1.7 Step 3. `useGraphCanvas` exposes `nodes`, `edges`, `selectedId`, `setSelectedId`, `mergeNeighbors`, `clear`, `replaceProjection`, `restore` — all used consistently in Tasks 5.2, 5.4, 5.6. `computePathToRoot(selectedId, localKbName)` returns `OverlayEdge[]` in 5.3 and is used as such in 5.6. `DocumentSearchHit` defined in 0.1, reused with the same shape in 2.1, 4.2, 4.5.

4. **Acknowledged carry-overs** — Task 3.1 leaves `@ts-ignore`-style stubs in `InvestigatePage`/`QueryPage`/`OperatePage`; those files are deleted in Task 3.2 Step 8. Task 4.6 assumes `context.guru` test harness has `ingest_document`, etc.; those are introduced in Task 1.8 Step 2.
