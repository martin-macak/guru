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
