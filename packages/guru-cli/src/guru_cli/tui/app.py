from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.widgets import Footer, Header, Input, Static

from .bindings import APP_BINDINGS
from .controllers.investigate import InvestigateController
from .state import WorkbenchState
from .widgets.detail_panel import DetailPanelWidget
from .widgets.investigation import InvestigationPane
from .widgets.knowledge_tree import KnowledgeTreeWidget


class WorkbenchApp(App[None]):
    TITLE = "Guru"
    SUB_TITLE = "Knowledge Workbench"
    BINDINGS = APP_BINDINGS

    def __init__(self, session=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self._investigate = InvestigateController(session) if session is not None else None
        self._state = WorkbenchState()
        self.selected_mode = "investigate"
        self.tree_visible = True
        self.detail_visible = True
        self._mode_label: Static | None = None
        self._body_label: Static | None = None
        self._tree_label: Static | None = None
        self._detail_label: Static | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="workbench-root"):
            yield Static("", id="mode-label")
            yield Static("Knowledge Workbench TUI", id="body-label")
            yield KnowledgeTreeWidget("", id="knowledge-tree")
            yield InvestigationPane(id="investigation-pane")
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
        self.set_focus(None)
        self._sync_view()

    def action_switch_mode(self, mode: str) -> None:
        if mode not in {"investigate", "graph", "query", "operate"}:
            raise ValueError(f"Unknown mode: {mode}")
        self.selected_mode = mode
        self._sync_view()

    def action_toggle_tree(self) -> None:
        self.tree_visible = not self.tree_visible
        tree = self.query_one("#knowledge-tree")
        tree.display = not self.tree_visible
        self._sync_view()

    def action_toggle_detail(self) -> None:
        self.detail_visible = not self.detail_visible
        detail = self.query_one("#detail-panel")
        detail.display = not self.detail_visible
        self._sync_view()

    def _sync_view(self) -> None:
        if self._mode_label is not None:
            self._mode_label.update(f"Mode: {self.selected_mode.title()}")
        if self._body_label is not None:
            self._body_label.update("Knowledge Workbench TUI")
        if self._tree_label is not None:
            state = "visible" if self.tree_visible else "hidden"
            self._tree_label.update(f"Tree: {state}")
        if self._detail_label is not None:
            state = "visible" if self.detail_visible else "hidden"
            self._detail_label.update(f"Detail: {state}")

    def on_key(self, event: Key) -> None:
        if event.key != "slash":
            return
        search_input = self.query_one("#investigation-input", Input)
        search_input.disabled = False
        search_input.focus()
        event.stop()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "investigation-input" or self._investigate is None:
            return
        self._state, hits = await self._investigate.search(self._state, event.value)
        first_hit = hits[0] if hits else None
        content = (first_hit.title or first_hit.file_path) if first_hit is not None else ""
        self.query_one("#results", Static).update(content)
        event.input.disabled = True
        self.set_focus(None)


def run_tui() -> None:
    WorkbenchApp().run()
