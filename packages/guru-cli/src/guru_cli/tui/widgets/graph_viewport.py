from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from guru_cli.tui.view_models import GraphEdgeVM, GraphNodeVM


class GraphViewportWidget(Static):
    DEFAULT_CSS = "#graph-viewport { display: none; }"

    def __init__(self, content: str = "", **kwargs) -> None:
        super().__init__(content, **kwargs)
        self._plain_text = content

    def render_graph(self, nodes: list[GraphNodeVM], edges: list[GraphEdgeVM]) -> None:
        lines: list[str] = []
        if not nodes:
            lines.append("Graph: no selection")
        else:
            lines.append("Graph nodes:")
            for node in nodes:
                lines.append(f"- {node.label} ({node.node_id})")
        if edges:
            lines.append("")
            lines.append("Graph edges:")
            for edge in edges:
                lines.append(f"- {edge.from_id} -> {edge.to_id} [{edge.rel_type}]")
        self._plain_text = "\n".join(lines)
        super().update(self._plain_text)

    def update(self, content: str = "") -> None:
        self._plain_text = content
        super().update(content)

    @property
    def renderable(self) -> Text:
        return Text(self._plain_text)
