from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Static


class ResultsWidget(Static):
    def __init__(self, content: str = "", **kwargs) -> None:
        super().__init__(content, **kwargs)
        self._plain_text = content

    def update(self, content: str = "") -> None:
        self._plain_text = content
        super().update(content)

    @property
    def renderable(self) -> Text:
        return Text(self._plain_text)


class InvestigationPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search knowledge base", id="investigation-input")
        yield ResultsWidget("", id="results")
