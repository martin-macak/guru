from __future__ import annotations

from dataclasses import dataclass, field


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
