from __future__ import annotations

from dataclasses import replace
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.widgets import Button, Footer, Header, Input, Static

from guru_core.graph_errors import GraphUnavailable

from .bindings import APP_BINDINGS
from .controllers.graph import GraphController
from .controllers.investigate import InvestigateController
from .controllers.operate import OperateController
from .controllers.query import QueryController
from .state import WorkbenchMode, WorkbenchState
from .widgets.detail_panel import DetailPanelWidget
from .widgets.graph_viewport import GraphViewportWidget
from .widgets.investigation import InvestigationPane
from .widgets.knowledge_tree import KnowledgeTreeWidget
from .widgets.operate import OperatePane
from .widgets.query import QueryPane


class WorkbenchApp(App[None]):
    TITLE = "Guru"
    SUB_TITLE = "Knowledge Workbench"
    BINDINGS: ClassVar = [*APP_BINDINGS, ("ctrl+enter", "submit_query", "Run Query")]

    def __init__(self, session=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self._investigate = InvestigateController(session) if session is not None else None
        self._graph = GraphController(session) if session is not None else None
        self._operate = OperateController(session) if session is not None else None
        self._query = QueryController(session) if session is not None else None
        self._state = WorkbenchState()
        self._mode_label: Static | None = None
        self._body_label: Static | None = None
        self._tree_label: Static | None = None
        self._detail_label: Static | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="workbench-root"):
            yield Static("", id="mode-label")
            yield Static("Knowledge Workbench TUI", id="body-label")
            yield GraphViewportWidget("", id="graph-viewport")
            yield KnowledgeTreeWidget("", id="knowledge-tree")
            yield InvestigationPane(id="investigation-pane")
            yield QueryPane(id="query-pane")
            yield OperatePane(id="operate-pane")
            yield DetailPanelWidget("", id="detail-panel")
            yield Static("", id="tree-label")
            yield Static("", id="detail-label")
        yield Footer()

    def on_mount(self) -> None:
        self._mode_label = self.query_one("#mode-label", Static)
        self._body_label = self.query_one("#body-label", Static)
        self._tree_label = self.query_one("#tree-label", Static)
        self._detail_label = self.query_one("#detail-label", Static)
        self.query_one("#investigation-input", Input).disabled = True
        self.query_one("#query-input", Input).disabled = True
        self.query_one("#graph-viewport").display = self.selected_mode == WorkbenchMode.GRAPH.value
        self.query_one("#knowledge-tree").display = self.tree_visible
        self.query_one("#detail-panel").display = self.detail_visible
        self.query_one("#investigation-pane").display = (
            self.selected_mode == WorkbenchMode.INVESTIGATE.value
        )
        self.query_one("#query-pane").display = self.selected_mode == WorkbenchMode.QUERY.value
        self.query_one("#operate-pane").display = self.selected_mode == WorkbenchMode.OPERATE.value
        self.set_focus(None)
        self._sync_view()

    async def action_switch_mode(self, mode: str) -> None:
        if mode not in {"investigate", "graph", "query", "operate"}:
            raise ValueError(f"Unknown mode: {mode}")
        self._state = replace(self._state, mode=WorkbenchMode(mode))
        if mode == WorkbenchMode.GRAPH.value and self._graph is not None:
            await self._refresh_graph_view()
        if mode == WorkbenchMode.OPERATE.value and self._operate is not None:
            await self._refresh_operate_status()
        self._sync_view()

    def action_toggle_tree(self) -> None:
        panels = replace(self._state.panels, tree_visible=not self.tree_visible)
        self._state = replace(self._state, panels=panels)
        tree = self.query_one("#knowledge-tree")
        tree.display = self.tree_visible
        self._sync_view()

    def action_toggle_detail(self) -> None:
        panels = replace(self._state.panels, detail_visible=not self.detail_visible)
        self._state = replace(self._state, panels=panels)
        detail = self.query_one("#detail-panel")
        detail.display = self.detail_visible
        self._sync_view()

    def _sync_view(self) -> None:
        if self._mode_label is not None:
            self._mode_label.update(f"Mode: {self.selected_mode.title()}")
        if self._body_label is not None:
            self._body_label.update("Knowledge Workbench TUI")
        self.query_one("#investigation-pane").display = (
            self.selected_mode == WorkbenchMode.INVESTIGATE.value
        )
        self.query_one("#graph-viewport").display = self.selected_mode == WorkbenchMode.GRAPH.value
        query_mode_selected = self.selected_mode == WorkbenchMode.QUERY.value
        self.query_one("#query-pane").display = query_mode_selected
        self.query_one("#query-input", Input).disabled = not query_mode_selected
        self.query_one("#operate-pane").display = self.selected_mode == WorkbenchMode.OPERATE.value
        if self._tree_label is not None:
            state = "visible" if self.tree_visible else "hidden"
            self._tree_label.update(f"Tree: {state}")
        if self._detail_label is not None:
            state = "visible" if self.detail_visible else "hidden"
            self._detail_label.update(f"Detail: {state}")

    async def on_key(self, event: Key) -> None:
        if event.key == "slash":
            search_input = self.query_one("#investigation-input", Input)
            search_input.disabled = False
            search_input.focus()
            event.stop()
            return

    async def action_submit_query(self) -> None:
        if self.selected_mode != WorkbenchMode.QUERY.value or self._query is None:
            return
        if not self._query.is_available():
            self.query_one("#query-results", Static).update("Graph unavailable")
            return
        query_input = self.query_one("#query-input", Input)
        try:
            columns, rows, elapsed_ms = await self._query.run_query(query_input.value)
        except GraphUnavailable as exc:
            self.query_one("#query-results", Static).update(f"Graph unavailable: {exc}")
            return
        self.query_one("#query-results", Static).update(
            self._format_query_body(columns, rows, elapsed_ms)
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "investigation-input" or self._investigate is None:
            return
        self._state, hits = await self._investigate.search(self._state, event.value)
        first_hit = hits[0] if hits else None
        content = (first_hit.title or first_hit.file_path) if first_hit is not None else ""
        self.query_one("#results", Static).update(content)
        event.input.disabled = True
        self.set_focus(None)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._operate is None or self.selected_mode != WorkbenchMode.OPERATE.value:
            return
        if event.button.id == "operate-refresh":
            await self._refresh_operate_status()
        if event.button.id == "operate-reindex":
            accepted = await self._operate.reindex()
            await self._refresh_operate_status(
                message=f"{accepted.message} [{accepted.status}] (job {accepted.job_id})"
            )

    @property
    def selected_mode(self) -> str:
        return self._state.mode.value

    @property
    def tree_visible(self) -> bool:
        return self._state.panels.tree_visible

    @property
    def detail_visible(self) -> bool:
        return self._state.panels.detail_visible

    async def _refresh_operate_status(self, *, message: str | None = None) -> None:
        if self._operate is None:
            return
        snapshot = await self._operate.refresh()
        body = self.query_one("#operate-body", Static)
        body.update(self._format_operate_body(snapshot, message=message))

    async def _refresh_graph_view(self) -> None:
        if self._graph is None:
            return
        viewport = self.query_one("#graph-viewport", GraphViewportWidget)
        node_id = self._state.selected_node_id
        if node_id is None:
            viewport.render_graph([], [])
            return
        nodes, edges = await self._graph.load_neighborhood(node_id, depth=1)
        viewport.render_graph(nodes, edges)

    def _format_operate_body(self, snapshot, *, message: str | None = None) -> str:
        graph_line = "reachable" if snapshot.graph_reachable else "unreachable"
        lines = []
        if message is not None:
            lines.extend([message, ""])
        lines.extend(
            [
                f"documents: {snapshot.document_count}",
                f"chunks: {snapshot.chunk_count}",
                f"graph: {graph_line}",
            ]
        )
        return "\n".join(lines)

    def _format_query_body(
        self, columns: list[str], rows: list[list[object]], elapsed_ms: float
    ) -> str:
        lines = []
        if columns:
            lines.append(" | ".join(columns))
        for row in rows:
            lines.append(" | ".join(str(value) for value in row))
        lines.append(f"elapsed: {elapsed_ms:.1f} ms")
        return "\n".join(lines)


def run_tui() -> None:
    WorkbenchApp().run()
