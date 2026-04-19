from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Static


class OperateBody(Static):
    def __init__(self, content: str = "", **kwargs) -> None:
        super().__init__(content, **kwargs)
        self._plain_text = content

    def update(self, content: str = "") -> None:
        self._plain_text = content
        super().update(content)

    @property
    def renderable(self) -> Text:
        return Text(self._plain_text)


class OperatePane(Vertical):
    DEFAULT_CSS = "#operate-pane { display: none; }"

    def compose(self) -> ComposeResult:
        yield Button("Refresh", id="operate-refresh")
        yield Button("Reindex", id="operate-reindex")
        yield OperateBody("", id="operate-body")
