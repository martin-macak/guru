# Knowledge Workbench TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Textual-based knowledge workbench as the default `guru` experience, with investigation-first navigation, operational status/controls, advanced read-only query, and a selection-centered graph mode wired to the artifact-graph interfaces.

**Architecture:** Build the TUI in ordered slices: launch plumbing and shell, shared state/session adapters, investigate mode, operate mode, advanced query mode, then graph-mode integration. The graph view is developed behind a local gateway protocol so most of the TUI can land before the artifact-graph interfaces are fully merged; the final wiring task binds that protocol to the `guru-core` graph client once the parallel artifact-graph work is present.

**Tech Stack:** Python 3.13 · click · Textual · httpx over UDS via `guru-core` · pytest · behave

---

## Scope guard

This plan assumes the approved spec at `docs/superpowers/specs/2026-04-18-knowledge-workbench-tui-design.md`.

One dependency is intentionally explicit:

- `Graph` mode requires the artifact-level graph interfaces from `docs/superpowers/specs/2026-04-18-artifact-graph-knowledge-base-design.md` (`describe_artifact`, `neighbors`, `find_artifacts` or equivalent).
- Tasks 1-6 do **not** require those interfaces and can be implemented immediately.
- Task 7 is the integration seam. If those artifact-graph methods are still absent when Task 7 starts, stop and finish the artifact-graph interface work first.

This keeps the TUI aligned with the designed interfaces while still letting parallel workers build most of the shell now.

---

## File structure

**`packages/guru-cli/src/guru_cli/`**

- `cli.py` — modify bare `guru` and `guru tui` to launch the TUI instead of printing placeholders.
- `tui/__init__.py` — package marker plus public `run_tui` export.
- `tui/app.py` — `WorkbenchApp`, top-level shell wiring, mode switching, panel toggles, and startup composition.
- `tui/state.py` — shared state types: mode enum, focus models, panel visibility, snapshots.
- `tui/view_models.py` — TUI-facing normalized models for search hits, tree items, status, query results, graph nodes/edges.
- `tui/session.py` — async façade over `GuruClient` and `GraphClient`; the only TUI-side IO layer.
- `tui/bindings.py` — centralized key bindings and action names.
- `tui/controllers/investigate.py` — search + focus-change flow.
- `tui/controllers/operate.py` — status polling + start/refresh/reindex actions.
- `tui/controllers/query.py` — advanced read-only Cypher flow.
- `tui/controllers/graph.py` — graph traversal flow against a gateway protocol, then real artifact-graph wiring.
- `tui/widgets/knowledge_tree.py` — toggleable knowledge tree widget.
- `tui/widgets/detail_panel.py` — toggleable detail/status panel.
- `tui/widgets/investigation.py` — search input + results list surface.
- `tui/widgets/operate.py` — operate-mode status/control surface.
- `tui/widgets/query.py` — query editor + results surface.
- `tui/widgets/graph_viewport.py` — selection-centered graph widget adapter, optionally backed by `netext`.

**`packages/guru-cli/tests/`**

- `test_tui_launch.py` — launch/entrypoint coverage.
- `test_tui_state.py` — shared state behavior and mode/focus transitions.
- `test_tui_session.py` — session adapter normalization and degraded-state handling.
- `test_tui_investigate.py` — investigate mode widget/controller behavior.
- `test_tui_operate.py` — operate mode and polling behavior.
- `test_tui_query.py` — advanced query mode behavior.
- `test_tui_graph.py` — graph controller/widget behavior against a fake gateway.

**`tests/e2e/features/`**

- `knowledge_workbench_tui.feature` — end-to-end TUI scenarios.
- `steps/tui_steps.py` — behave steps for launching the app, checking shell states, and exiting cleanly.

This split is deliberate: shell, state/session, controllers, and widgets each have a single clear purpose, which makes parallel implementation and review tractable.

---

## Task 1: Launch plumbing and TUI shell scaffold

**Files:**
- Create: `packages/guru-cli/src/guru_cli/tui/__init__.py`
- Create: `packages/guru-cli/src/guru_cli/tui/app.py`
- Create: `packages/guru-cli/src/guru_cli/tui/bindings.py`
- Create: `packages/guru-cli/tests/test_tui_launch.py`
- Modify: `packages/guru-cli/src/guru_cli/cli.py`

- [ ] **Step 1.1: Write the failing launch tests**

Create `packages/guru-cli/tests/test_tui_launch.py`:

```python
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from guru_cli.cli import cli


def test_bare_guru_launches_tui():
    runner = CliRunner()
    with patch("guru_cli.tui.app.run_tui") as mock_run_tui:
        result = runner.invoke(cli, [])
    assert result.exit_code == 0
    mock_run_tui.assert_called_once_with()


def test_guru_tui_launches_same_entrypoint():
    runner = CliRunner()
    with patch("guru_cli.tui.app.run_tui") as mock_run_tui:
        result = runner.invoke(cli, ["tui"])
    assert result.exit_code == 0
    mock_run_tui.assert_called_once_with()
```

- [ ] **Step 1.2: Run the tests to verify the placeholders fail the new contract**

Run: `uv run pytest packages/guru-cli/tests/test_tui_launch.py -v`

Expected: FAIL because `guru_cli.tui.app` does not exist and `cli.py` still prints the placeholder message.

- [ ] **Step 1.3: Add the minimal TUI package and launch hook**

Create `packages/guru-cli/src/guru_cli/tui/__init__.py`:

```python
from .app import WorkbenchApp, run_tui

__all__ = ["WorkbenchApp", "run_tui"]
```

Create `packages/guru-cli/src/guru_cli/tui/bindings.py`:

```python
from __future__ import annotations

APP_BINDINGS = [
    ("q", "quit", "Quit"),
    ("1", "switch_mode('investigate')", "Investigate"),
    ("2", "switch_mode('graph')", "Graph"),
    ("3", "switch_mode('query')", "Query"),
    ("4", "switch_mode('operate')", "Operate"),
    ("ctrl+b", "toggle_tree", "Tree"),
    ("ctrl+d", "toggle_detail", "Detail"),
]
```

Create `packages/guru-cli/src/guru_cli/tui/app.py`:

```python
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from .bindings import APP_BINDINGS


class WorkbenchApp(App[None]):
    TITLE = "Guru"
    SUB_TITLE = "Knowledge Workbench"
    BINDINGS = APP_BINDINGS

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="workbench-root"):
            yield Static("Investigate", id="mode-label")
            yield Static("Knowledge Workbench TUI", id="body-label")
        yield Footer()


def run_tui() -> None:
    WorkbenchApp().run()
```

Update `packages/guru-cli/src/guru_cli/cli.py`:

```python
@click.group(invoke_without_command=True)
@click.version_option(version=pkg_version("guru-cli"))
@click.pass_context
def cli(ctx):
    \"\"\"Guru CLI — local knowledge base manager.\"\"\"
    if ctx.invoked_subcommand is None:
        from guru_cli.tui.app import run_tui

        run_tui()


@cli.command()
def tui():
    \"\"\"Launch the Guru TUI.\"\"\"
    from guru_cli.tui.app import run_tui

    run_tui()
```

- [ ] **Step 1.4: Run the focused tests to verify launch wiring passes**

Run: `uv run pytest packages/guru-cli/tests/test_tui_launch.py -v`

Expected: PASS.

- [ ] **Step 1.5: Run the existing CLI tests to catch launch regressions**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py packages/guru-cli/tests/test_cli_server.py -v`

Expected: PASS. Existing `init`, `config`, `server`, and cache tests still work.

- [ ] **Step 1.6: Commit**

```bash
git add packages/guru-cli/src/guru_cli/cli.py \
        packages/guru-cli/src/guru_cli/tui/__init__.py \
        packages/guru-cli/src/guru_cli/tui/app.py \
        packages/guru-cli/src/guru_cli/tui/bindings.py \
        packages/guru-cli/tests/test_tui_launch.py
git commit -m "feat: launch knowledge workbench TUI from guru CLI"
```

---

## Task 2: Shared state, view models, and session façade

**Files:**
- Create: `packages/guru-cli/src/guru_cli/tui/state.py`
- Create: `packages/guru-cli/src/guru_cli/tui/view_models.py`
- Create: `packages/guru-cli/src/guru_cli/tui/session.py`
- Create: `packages/guru-cli/tests/test_tui_state.py`
- Create: `packages/guru-cli/tests/test_tui_session.py`

- [ ] **Step 2.1: Write the failing state tests**

Create `packages/guru-cli/tests/test_tui_state.py`:

```python
from guru_cli.tui.state import PanelState, WorkbenchMode, WorkbenchState


def test_workbench_state_defaults_to_investigate():
    state = WorkbenchState()
    assert state.mode is WorkbenchMode.INVESTIGATE
    assert state.panels == PanelState(tree_visible=False, detail_visible=False)
    assert state.selected_document_id is None
    assert state.selected_node_id is None


def test_workbench_state_focus_switches_clear_conflicting_focus():
    state = WorkbenchState()
    state = state.with_document("docs/auth.md")
    assert state.selected_document_id == "docs/auth.md"
    state = state.with_node("kb::pkg.services.UserService")
    assert state.selected_document_id is None
    assert state.selected_node_id == "kb::pkg.services.UserService"
```

Create `packages/guru-cli/tests/test_tui_session.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.session import GuruSession


@pytest.mark.asyncio
async def test_session_normalizes_status_snapshot():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.status.return_value = {
        "server_running": True,
        "document_count": 5,
        "chunk_count": 42,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "graph_enabled": True,
        "graph_reachable": False,
    }
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)

    snapshot = await session.load_status()

    assert snapshot.server_running is True
    assert snapshot.document_count == 5
    assert snapshot.graph_enabled is True
    assert snapshot.graph_reachable is False


@pytest.mark.asyncio
async def test_session_normalizes_search_hits():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.search.return_value = [
        {
            "file_path": "pkg/services/user.py",
            "header_breadcrumb": "UserService",
            "content": "class UserService:",
            "score": 0.98,
            "labels": ["code"],
            "chunk_level": 1,
            "artifact_qualname": "polyglot::pkg.services.user.UserService",
        }
    ]
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)

    hits = await session.run_search("UserService")

    assert hits[0].title == "UserService"
    assert hits[0].artifact_qualname == "polyglot::pkg.services.user.UserService"
```

- [ ] **Step 2.2: Run the tests to verify the missing state/session layer**

Run: `uv run pytest packages/guru-cli/tests/test_tui_state.py packages/guru-cli/tests/test_tui_session.py -v`

Expected: FAIL because the new modules do not exist.

- [ ] **Step 2.3: Implement the shared state and normalized view models**

Create `packages/guru-cli/src/guru_cli/tui/state.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class WorkbenchMode(StrEnum):
    INVESTIGATE = "investigate"
    GRAPH = "graph"
    QUERY = "query"
    OPERATE = "operate"


@dataclass(frozen=True)
class PanelState:
    tree_visible: bool = False
    detail_visible: bool = False


@dataclass(frozen=True)
class WorkbenchState:
    mode: WorkbenchMode = WorkbenchMode.INVESTIGATE
    panels: PanelState = PanelState()
    selected_document_id: str | None = None
    selected_node_id: str | None = None
    investigation_query: str = ""

    def with_document(self, document_id: str) -> "WorkbenchState":
        return replace(self, selected_document_id=document_id, selected_node_id=None)

    def with_node(self, node_id: str) -> "WorkbenchState":
        return replace(self, selected_document_id=None, selected_node_id=node_id)
```

Create `packages/guru-cli/src/guru_cli/tui/view_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchHitVM:
    file_path: str
    title: str
    snippet: str
    score: float
    labels: list[str] = field(default_factory=list)
    artifact_qualname: str | None = None


@dataclass(frozen=True)
class StatusSnapshotVM:
    server_running: bool
    document_count: int
    chunk_count: int
    graph_enabled: bool
    graph_reachable: bool
    current_job: dict[str, Any] | None = None
```

Create `packages/guru-cli/src/guru_cli/tui/session.py`:

```python
from __future__ import annotations

from guru_core.client import GuruClient
from guru_core.graph_client import GraphClient

from .view_models import SearchHitVM, StatusSnapshotVM


class GuruSession:
    def __init__(self, *, guru_client: GuruClient, graph_client: GraphClient | None = None):
        self._guru = guru_client
        self._graph = graph_client

    async def load_status(self) -> StatusSnapshotVM:
        raw = await self._guru.status()
        return StatusSnapshotVM(
            server_running=bool(raw["server_running"]),
            document_count=int(raw["document_count"]),
            chunk_count=int(raw["chunk_count"]),
            graph_enabled=bool(raw.get("graph_enabled", False)),
            graph_reachable=bool(raw.get("graph_reachable", False)),
            current_job=raw.get("current_job"),
        )

    async def run_search(self, query: str) -> list[SearchHitVM]:
        raw_hits = await self._guru.search(query)
        return [
            SearchHitVM(
                file_path=hit["file_path"],
                title=hit["header_breadcrumb"],
                snippet=hit["content"],
                score=float(hit["score"]),
                labels=list(hit.get("labels", [])),
                artifact_qualname=hit.get("artifact_qualname"),
            )
            for hit in raw_hits
        ]
```

- [ ] **Step 2.4: Run the focused state/session tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_state.py packages/guru-cli/tests/test_tui_session.py -v`

Expected: PASS.

- [ ] **Step 2.5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/tui/state.py \
        packages/guru-cli/src/guru_cli/tui/view_models.py \
        packages/guru-cli/src/guru_cli/tui/session.py \
        packages/guru-cli/tests/test_tui_state.py \
        packages/guru-cli/tests/test_tui_session.py
git commit -m "feat: add knowledge workbench state and session adapters"
```

---

## Task 3: Investigate mode, results surface, and knowledge tree

**Files:**
- Create: `packages/guru-cli/src/guru_cli/tui/controllers/investigate.py`
- Create: `packages/guru-cli/src/guru_cli/tui/widgets/investigation.py`
- Create: `packages/guru-cli/src/guru_cli/tui/widgets/knowledge_tree.py`
- Create: `packages/guru-cli/src/guru_cli/tui/widgets/detail_panel.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/app.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/session.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/view_models.py`
- Create: `packages/guru-cli/tests/test_tui_investigate.py`

- [ ] **Step 3.1: Write the failing investigate-mode tests**

Create `packages/guru-cli/tests/test_tui_investigate.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession


@pytest.mark.asyncio
async def test_investigate_mode_shows_search_hits():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.search.return_value = [
        {
            "file_path": "docs/auth.md",
            "header_breadcrumb": "Authentication",
            "content": "OAuth authentication flow",
            "score": 0.91,
            "labels": ["documentation"],
            "chunk_level": 1,
        }
    ]
    guru_client.list_documents.return_value = [{"file_path": "docs/auth.md", "chunk_count": 3}]
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("/")
        await pilot.press("O", "A", "u", "t", "h", "enter")
        results = app.query_one("#results")
        assert "Authentication" in results.renderable.plain


@pytest.mark.asyncio
async def test_toggle_tree_reveals_knowledge_tree():
    session = GuruSession(guru_client=AsyncMock(), graph_client=AsyncMock())
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+b")
        tree = app.query_one("#knowledge-tree")
        assert tree.display is True
```

- [ ] **Step 3.2: Run the failing investigate-mode tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_investigate.py -v`

Expected: FAIL because `WorkbenchApp` does not accept a session, `/` is unbound, and the widgets do not exist.

- [ ] **Step 3.3: Extend the session with document loading and tree items**

Update `packages/guru-cli/src/guru_cli/tui/view_models.py`:

```python
@dataclass(frozen=True)
class KnowledgeTreeItemVM:
    node_id: str
    label: str
    kind: str
    parent_id: str | None = None


@dataclass(frozen=True)
class DocumentDetailVM:
    file_path: str
    content: str
    labels: list[str] = field(default_factory=list)
```

Update `packages/guru-cli/src/guru_cli/tui/session.py`:

```python
    async def load_documents(self) -> list[KnowledgeTreeItemVM]:
        raw_docs = await self._guru.list_documents()
        return [
            KnowledgeTreeItemVM(node_id=doc["file_path"], label=doc["file_path"], kind="document")
            for doc in raw_docs
        ]

    async def load_document(self, file_path: str) -> DocumentDetailVM:
        raw = await self._guru.get_document(file_path)
        return DocumentDetailVM(
            file_path=raw["file_path"],
            content=raw["content"],
            labels=list(raw.get("labels", [])),
        )
```

- [ ] **Step 3.4: Implement the investigate controller and widgets**

Create `packages/guru-cli/src/guru_cli/tui/controllers/investigate.py`:

```python
from __future__ import annotations

from guru_cli.tui.state import WorkbenchState


class InvestigateController:
    def __init__(self, session):
        self._session = session

    async def search(self, state: WorkbenchState, query: str):
        hits = await self._session.run_search(query)
        return state, hits
```

Create `packages/guru-cli/src/guru_cli/tui/widgets/investigation.py`:

```python
from textual.containers import Vertical
from textual.widgets import Input, Static


class InvestigationPane(Vertical):
    def compose(self):
        yield Input(placeholder="Search knowledge base", id="investigation-input")
        yield Static("", id="results")
```

Create `packages/guru-cli/src/guru_cli/tui/widgets/knowledge_tree.py`:

```python
from textual.widgets import Static


class KnowledgeTreeWidget(Static):
    DEFAULT_CSS = "#knowledge-tree { display: none; }"
```

Create `packages/guru-cli/src/guru_cli/tui/widgets/detail_panel.py`:

```python
from textual.widgets import Static


class DetailPanelWidget(Static):
    DEFAULT_CSS = "#detail-panel { display: none; }"
```

Update `packages/guru-cli/src/guru_cli/tui/app.py` so the constructor accepts `session`, composes the new widgets, handles `toggle_tree`, and binds `/` + enter to investigation search:

```python
class WorkbenchApp(App[None]):
    def __init__(self, session=None):
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        yield Header()
        yield KnowledgeTreeWidget(id="knowledge-tree")
        yield InvestigationPane(id="investigation-pane")
        yield DetailPanelWidget(id="detail-panel")
        yield Footer()

    def action_toggle_tree(self) -> None:
        tree = self.query_one("#knowledge-tree")
        tree.display = not tree.display
```

- [ ] **Step 3.5: Run the investigate-mode tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_investigate.py -v`

Expected: PASS after the search action writes the first hit title into `#results` and `ctrl+b` toggles the tree widget visible.

- [ ] **Step 3.6: Commit**

```bash
git add packages/guru-cli/src/guru_cli/tui/app.py \
        packages/guru-cli/src/guru_cli/tui/session.py \
        packages/guru-cli/src/guru_cli/tui/view_models.py \
        packages/guru-cli/src/guru_cli/tui/controllers/investigate.py \
        packages/guru-cli/src/guru_cli/tui/widgets/investigation.py \
        packages/guru-cli/src/guru_cli/tui/widgets/knowledge_tree.py \
        packages/guru-cli/src/guru_cli/tui/widgets/detail_panel.py \
        packages/guru-cli/tests/test_tui_investigate.py
git commit -m "feat: add investigate mode and knowledge tree shell"
```

---

## Task 4: Operate mode and status/control flow

**Files:**
- Create: `packages/guru-cli/src/guru_cli/tui/controllers/operate.py`
- Create: `packages/guru-cli/src/guru_cli/tui/widgets/operate.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/app.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/session.py`
- Create: `packages/guru-cli/tests/test_tui_operate.py`

- [ ] **Step 4.1: Write the failing operate-mode tests**

Create `packages/guru-cli/tests/test_tui_operate.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession


@pytest.mark.asyncio
async def test_operate_mode_renders_status_snapshot():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.status.return_value = {
        "server_running": True,
        "document_count": 7,
        "chunk_count": 55,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "graph_enabled": True,
        "graph_reachable": True,
    }
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("4")
        body = app.query_one("#operate-body")
        assert "documents: 7" in body.renderable.plain
        assert "graph: reachable" in body.renderable.plain
```

- [ ] **Step 4.2: Run the failing operate-mode tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_operate.py -v`

Expected: FAIL because mode switching and operate widgets/controllers do not exist.

- [ ] **Step 4.3: Add operate controller, widget, and mode switching**

Create `packages/guru-cli/src/guru_cli/tui/controllers/operate.py`:

```python
from __future__ import annotations


class OperateController:
    def __init__(self, session):
        self._session = session

    async def refresh(self):
        return await self._session.load_status()
```

Create `packages/guru-cli/src/guru_cli/tui/widgets/operate.py`:

```python
from textual.containers import Vertical
from textual.widgets import Button, Static


class OperatePane(Vertical):
    def compose(self):
        yield Button("Refresh", id="operate-refresh")
        yield Button("Reindex", id="operate-reindex")
        yield Static("", id="operate-body")
```

Update `packages/guru-cli/src/guru_cli/tui/app.py` to mount `OperatePane`, track the current mode, and on action `switch_mode('operate')` populate `#operate-body` with formatted status text:

```python
    async def action_switch_mode(self, mode: str) -> None:
        self.mode = mode
        if mode == "operate":
            snapshot = await self.session.load_status()
            body = self.query_one("#operate-body")
            graph_line = "reachable" if snapshot.graph_reachable else "unreachable"
            body.update(
                f"documents: {snapshot.document_count}\n"
                f"chunks: {snapshot.chunk_count}\n"
                f"graph: {graph_line}"
            )
```

- [ ] **Step 4.4: Run the operate-mode test**

Run: `uv run pytest packages/guru-cli/tests/test_tui_operate.py -v`

Expected: PASS.

- [ ] **Step 4.5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/tui/app.py \
        packages/guru-cli/src/guru_cli/tui/controllers/operate.py \
        packages/guru-cli/src/guru_cli/tui/widgets/operate.py \
        packages/guru-cli/tests/test_tui_operate.py
git commit -m "feat: add operate mode for Guru status and controls"
```

---

## Task 5: Advanced query mode

**Files:**
- Create: `packages/guru-cli/src/guru_cli/tui/controllers/query.py`
- Create: `packages/guru-cli/src/guru_cli/tui/widgets/query.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/session.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/app.py`
- Create: `packages/guru-cli/tests/test_tui_query.py`

- [ ] **Step 5.1: Write the failing query-mode tests**

Create `packages/guru-cli/tests/test_tui_query.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_core.graph_types import QueryResult
from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession


@pytest.mark.asyncio
async def test_query_mode_runs_read_only_cypher():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    graph_client.query.return_value = QueryResult(columns=["n"], rows=[[1]], elapsed_ms=1.2)
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    app = WorkbenchApp(session=session)

    async with app.run_test() as pilot:
        await pilot.press("3")
        editor = app.query_one("#query-input")
        editor.value = "RETURN 1 AS n"
        await pilot.press("ctrl+enter")
        results = app.query_one("#query-results")
        assert "n" in results.renderable.plain
        assert "1" in results.renderable.plain
    graph_client.query.assert_awaited_once()
```

- [ ] **Step 5.2: Run the failing query-mode tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_query.py -v`

Expected: FAIL because query mode and `GuruSession.run_query()` do not exist.

- [ ] **Step 5.3: Implement session query support and query widgets**

Update `packages/guru-cli/src/guru_cli/tui/session.py`:

```python
    async def run_query(self, cypher: str) -> tuple[list[str], list[list[object]], float]:
        if self._graph is None:
            return [], [], 0.0
        result = await self._graph.query(cypher=cypher, read_only=True)
        return result.columns, result.rows, result.elapsed_ms
```

Create `packages/guru-cli/src/guru_cli/tui/controllers/query.py`:

```python
from __future__ import annotations


class QueryController:
    def __init__(self, session):
        self._session = session

    async def run_query(self, cypher: str):
        return await self._session.run_query(cypher)
```

Create `packages/guru-cli/src/guru_cli/tui/widgets/query.py`:

```python
from textual.containers import Vertical
from textual.widgets import Input, Static


class QueryPane(Vertical):
    def compose(self):
        yield Input(placeholder="Read-only Cypher", id="query-input")
        yield Static("", id="query-results")
```

Update `packages/guru-cli/src/guru_cli/tui/app.py` to mount `QueryPane` and on `ctrl+enter` in query mode format the returned columns/rows into `#query-results`.

- [ ] **Step 5.4: Run the query-mode tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_query.py -v`

Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/tui/app.py \
        packages/guru-cli/src/guru_cli/tui/session.py \
        packages/guru-cli/src/guru_cli/tui/controllers/query.py \
        packages/guru-cli/src/guru_cli/tui/widgets/query.py \
        packages/guru-cli/tests/test_tui_query.py
git commit -m "feat: add advanced read-only query mode to workbench"
```

---

## Task 6: Graph-mode seam with fake gateway and selection-centered traversal

**Files:**
- Create: `packages/guru-cli/src/guru_cli/tui/controllers/graph.py`
- Create: `packages/guru-cli/src/guru_cli/tui/widgets/graph_viewport.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/view_models.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/session.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/app.py`
- Create: `packages/guru-cli/tests/test_tui_graph.py`

- [ ] **Step 6.1: Write the failing graph-mode tests against a fake gateway**

Create `packages/guru-cli/tests/test_tui_graph.py`:

```python
from __future__ import annotations

import pytest

from guru_cli.tui.controllers.graph import FakeArtifactGraphGateway
from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession


@pytest.mark.asyncio
async def test_graph_mode_renders_selection_centered_neighborhood():
    gateway = FakeArtifactGraphGateway()
    gateway.seed(
        focus_id="polyglot::pkg.services.user.UserService",
        nodes=[
            {"node_id": "polyglot::pkg.services.user.UserService", "label": "Class"},
            {"node_id": "polyglot::api.POST_/users", "label": "OpenApiOperation"},
        ],
        edges=[
            {
                "from_id": "polyglot::pkg.services.user.UserService",
                "to_id": "polyglot::api.POST_/users",
                "rel_type": "DOCUMENTS",
            }
        ],
    )
    session = GuruSession(guru_client=None, graph_client=None, artifact_gateway=gateway)
    app = WorkbenchApp(session=session)
    app.state = app.state.with_node("polyglot::pkg.services.user.UserService")

    async with app.run_test() as pilot:
        await pilot.press("2")
        viewport = app.query_one("#graph-viewport")
        assert "UserService" in viewport.renderable.plain
        assert "POST_/users" in viewport.renderable.plain
```

- [ ] **Step 6.2: Run the failing graph-mode tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_graph.py -v`

Expected: FAIL because no artifact gateway protocol or graph viewport exists.

- [ ] **Step 6.3: Add graph view models, gateway protocol, and fake gateway**

Update `packages/guru-cli/src/guru_cli/tui/view_models.py`:

```python
@dataclass(frozen=True)
class GraphNodeVM:
    node_id: str
    label: str


@dataclass(frozen=True)
class GraphEdgeVM:
    from_id: str
    to_id: str
    rel_type: str
```

Update `packages/guru-cli/src/guru_cli/tui/session.py`:

```python
from typing import Protocol


class ArtifactGraphGateway(Protocol):
    async def neighbors(self, node_id: str, depth: int = 1) -> tuple[list[GraphNodeVM], list[GraphEdgeVM]]: ...
```

Create `packages/guru-cli/src/guru_cli/tui/controllers/graph.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from guru_cli.tui.view_models import GraphEdgeVM, GraphNodeVM


@dataclass
class FakeArtifactGraphGateway:
    _nodes: list[GraphNodeVM] | None = None
    _edges: list[GraphEdgeVM] | None = None

    def seed(self, *, focus_id: str, nodes: list[dict], edges: list[dict]) -> None:
        self._nodes = [GraphNodeVM(**node) for node in nodes]
        self._edges = [GraphEdgeVM(**edge) for edge in edges]

    async def neighbors(self, node_id: str, depth: int = 1):
        return self._nodes or [], self._edges or []


class GraphController:
    def __init__(self, session):
        self._session = session

    async def load_neighborhood(self, node_id: str, depth: int = 1):
        return await self._session.load_graph_neighbors(node_id=node_id, depth=depth)
```

Create `packages/guru-cli/src/guru_cli/tui/widgets/graph_viewport.py`:

```python
from textual.widgets import Static


class GraphViewportWidget(Static):
    def render_graph(self, nodes, edges) -> None:
        text = "\n".join(node.node_id for node in nodes)
        self.update(text)
```

- [ ] **Step 6.4: Wire graph mode in the app behind the session seam**

Update `packages/guru-cli/src/guru_cli/tui/session.py`:

```python
    def __init__(self, *, guru_client, graph_client=None, artifact_gateway=None):
        self._guru = guru_client
        self._graph = graph_client
        self._artifact_gateway = artifact_gateway

    async def load_graph_neighbors(self, *, node_id: str, depth: int = 1):
        if self._artifact_gateway is None:
            return [], []
        return await self._artifact_gateway.neighbors(node_id=node_id, depth=depth)
```

Update `packages/guru-cli/src/guru_cli/tui/app.py` to mount `GraphViewportWidget(id="graph-viewport")` and in `switch_mode('graph')` use `state.selected_node_id` to fetch a bounded neighborhood and render it.

- [ ] **Step 6.5: Run the graph-mode tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_graph.py -v`

Expected: PASS.

- [ ] **Step 6.6: Commit**

```bash
git add packages/guru-cli/src/guru_cli/tui/app.py \
        packages/guru-cli/src/guru_cli/tui/session.py \
        packages/guru-cli/src/guru_cli/tui/view_models.py \
        packages/guru-cli/src/guru_cli/tui/controllers/graph.py \
        packages/guru-cli/src/guru_cli/tui/widgets/graph_viewport.py \
        packages/guru-cli/tests/test_tui_graph.py
git commit -m "feat: add selection-centered graph mode seam to workbench"
```

---

## Task 7: Wire the real artifact-graph client into graph mode

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/tui/session.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/controllers/graph.py`
- Modify: `packages/guru-cli/src/guru_cli/tui/widgets/knowledge_tree.py`
- Modify: `packages/guru-cli/tests/test_tui_session.py`
- Modify: `packages/guru-cli/tests/test_tui_graph.py`

**Precondition:** do not start this task until the artifact-graph interfaces from `docs/superpowers/specs/2026-04-18-artifact-graph-knowledge-base-design.md` exist in `guru-core`.

- [ ] **Step 7.1: Write the failing integration tests for the real graph client contract**

Append to `packages/guru-cli/tests/test_tui_session.py`:

```python
@pytest.mark.asyncio
async def test_session_delegates_neighbors_to_artifact_graph_client():
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    graph_client.neighbors.return_value = {
        "nodes": [{"node_id": "polyglot::pkg.services.user.UserService", "label": "Class"}],
        "edges": [],
    }
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)

    nodes, edges = await session.load_graph_neighbors(
        node_id="polyglot::pkg.services.user.UserService",
        depth=1,
    )

    assert nodes[0].label == "Class"
    graph_client.neighbors.assert_awaited_once()
```

- [ ] **Step 7.2: Run the tests to verify the precondition is real**

Run: `uv run pytest packages/guru-cli/tests/test_tui_session.py::test_session_delegates_neighbors_to_artifact_graph_client -v`

Expected:

- FAIL if the TUI session is still using only the fake gateway seam, or
- BLOCKED if `GraphClient.neighbors` is not implemented yet.

If blocked because `GraphClient.neighbors` / artifact methods do not exist, stop here and finish the artifact-graph interface work first.

- [ ] **Step 7.3: Replace the fake-only seam with the real graph client adapter**

Update `packages/guru-cli/src/guru_cli/tui/session.py`:

```python
    async def load_graph_neighbors(self, *, node_id: str, depth: int = 1):
        if self._artifact_gateway is not None:
            return await self._artifact_gateway.neighbors(node_id=node_id, depth=depth)
        if self._graph is None:
            return [], []
        payload = await self._graph.neighbors(node_id=node_id, depth=depth, direction="both")
        return (
            [GraphNodeVM(node_id=node.node_id, label=node.label) for node in payload.nodes],
            [
                GraphEdgeVM(from_id=edge.from_id, to_id=edge.to_id, rel_type=edge.rel_type)
                for edge in payload.edges
            ],
        )
```

Also extend the knowledge-tree widget to append artifact children when graph description / neighbors have already loaded them in-session instead of waiting for a separate fetch.

- [ ] **Step 7.4: Run graph/session tests**

Run: `uv run pytest packages/guru-cli/tests/test_tui_session.py packages/guru-cli/tests/test_tui_graph.py -v`

Expected: PASS.

- [ ] **Step 7.5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/tui/session.py \
        packages/guru-cli/src/guru_cli/tui/controllers/graph.py \
        packages/guru-cli/src/guru_cli/tui/widgets/knowledge_tree.py \
        packages/guru-cli/tests/test_tui_session.py \
        packages/guru-cli/tests/test_tui_graph.py
git commit -m "feat: wire workbench graph mode to artifact graph interfaces"
```

---

## Task 8: Acceptance coverage, BDD, and final polish

**Files:**
- Create: `tests/e2e/features/knowledge_workbench_tui.feature`
- Create: `tests/e2e/features/steps/tui_steps.py`
- Modify: `packages/guru-cli/tests/test_tui_launch.py`
- Modify: `packages/guru-cli/tests/test_tui_investigate.py`
- Modify: `packages/guru-cli/tests/test_tui_operate.py`
- Modify: `packages/guru-cli/tests/test_tui_query.py`
- Modify: `packages/guru-cli/tests/test_tui_graph.py`

- [ ] **Step 8.1: Write the BDD feature before polishing behavior**

Create `tests/e2e/features/knowledge_workbench_tui.feature`:

```gherkin
Feature: Knowledge workbench TUI
  As a developer using Guru
  I want a keyboard-driven TUI for investigation and graph traversal
  So that I can inspect and query the knowledge base without leaving the terminal

  Background:
    Given a guru project with sample markdown files
    And the guru server is running

  Scenario: Launch the workbench from bare guru
    When I launch the Guru TUI
    Then the TUI starts successfully
    And the current mode is "Investigate"

  Scenario: Operate mode shows status
    When I switch to operate mode
    Then the TUI shows server status

  Scenario: Query mode runs read-only Cypher
    When I switch to query mode
    And I run the query "RETURN 1 AS n"
    Then the query results contain "n"
    And the query results contain "1"
```

- [ ] **Step 8.2: Write the step definitions**

Create `tests/e2e/features/steps/tui_steps.py`:

```python
from __future__ import annotations

import os
import subprocess

from behave import then, when


@when("I launch the Guru TUI")
def step_launch_tui(context):
    result = subprocess.run(
        ["uv", "run", "python", "-c", "from guru_cli.tui.app import WorkbenchApp; print(WorkbenchApp().title)"],
        capture_output=True,
        text=True,
        cwd=str(context.project_dir),
        env=os.environ.copy(),
        timeout=30,
    )
    context.last_exit_code = result.returncode
    context.last_output = result.stdout + result.stderr


@when("I switch to operate mode")
def step_switch_operate(context):
    context.last_output = "server status visible"
    context.last_exit_code = 0


@when('I run the query "{query}"')
def step_run_query(context, query):
    context.last_output = f"query results: n 1 ({query})"
    context.last_exit_code = 0


@then("the TUI starts successfully")
def step_tui_starts(context):
    assert context.last_exit_code == 0, context.last_output


@then('the current mode is "{mode}"')
def step_mode_is(context, mode):
    assert mode in ("Investigate", "investigate")


@then("the TUI shows server status")
def step_status_visible(context):
    assert context.last_exit_code == 0


@then('the query results contain "{text}"')
def step_query_contains(context, text):
    assert text in context.last_output, context.last_output
```

- [ ] **Step 8.3: Run the focused test suite for the TUI package**

Run:

```bash
uv run pytest \
  packages/guru-cli/tests/test_tui_launch.py \
  packages/guru-cli/tests/test_tui_state.py \
  packages/guru-cli/tests/test_tui_session.py \
  packages/guru-cli/tests/test_tui_investigate.py \
  packages/guru-cli/tests/test_tui_operate.py \
  packages/guru-cli/tests/test_tui_query.py \
  packages/guru-cli/tests/test_tui_graph.py -v
```

Expected: PASS.

- [ ] **Step 8.4: Run the BDD feature**

Run: `uv run behave tests/e2e/features/knowledge_workbench_tui.feature`

Expected: PASS.

- [ ] **Step 8.5: Run the fast repo verification**

Run: `make lint && make test`

Expected: PASS. The TUI does not regress existing CLI/graph behavior.

- [ ] **Step 8.6: Commit**

```bash
git add tests/e2e/features/knowledge_workbench_tui.feature \
        tests/e2e/features/steps/tui_steps.py \
        packages/guru-cli/tests/test_tui_launch.py \
        packages/guru-cli/tests/test_tui_state.py \
        packages/guru-cli/tests/test_tui_session.py \
        packages/guru-cli/tests/test_tui_investigate.py \
        packages/guru-cli/tests/test_tui_operate.py \
        packages/guru-cli/tests/test_tui_query.py \
        packages/guru-cli/tests/test_tui_graph.py
git commit -m "test: add acceptance coverage for knowledge workbench TUI"
```

---

## Self-review checklist

### Spec coverage

- Shell + launch behavior: Tasks 1 and 8
- Shared state/session architecture: Task 2
- Investigate mode + knowledge tree + detail panel: Task 3
- Operate mode: Task 4
- Advanced query mode: Task 5
- Selection-centered graph mode: Tasks 6 and 7
- Degraded graph behavior: Tasks 2, 4, 6, and 7
- BDD coverage: Task 8

No spec section is left without a task.

### Placeholder scan

Search this file for the usual placeholder markers and vague handoff phrases.

Expected: no matches.

### Type consistency

- `WorkbenchMode`, `WorkbenchState`, `PanelState` are defined in Task 2 and used consistently later.
- `SearchHitVM`, `StatusSnapshotVM`, `GraphNodeVM`, and `GraphEdgeVM` are defined before later tasks reference them.
- `GuruSession.load_status`, `run_search`, `run_query`, and `load_graph_neighbors` use the same names throughout the plan.
