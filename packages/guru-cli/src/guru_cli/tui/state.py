from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    panels: PanelState = field(default_factory=PanelState)
    selected_document_id: str | None = None
    selected_node_id: str | None = None
    investigation_query: str = ""

    def with_document(self, document_id: str) -> WorkbenchState:
        return replace(self, selected_document_id=document_id, selected_node_id=None)

    def with_node(self, node_id: str) -> WorkbenchState:
        return replace(self, selected_document_id=None, selected_node_id=node_id)
