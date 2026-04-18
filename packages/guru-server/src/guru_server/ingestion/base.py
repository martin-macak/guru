from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from guru_core.types import Rule


@dataclass
class Chunk:
    content: str
    file_path: str
    header_breadcrumb: str
    chunk_level: int
    frontmatter: dict[str, Any] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    parent_chunk_id: str | None = None
    chunk_id: str | None = None
    content_type: str = "text"  # "text" | "code" | "table" | "mixed"
    # Artifact-graph metadata (PR-1 additions):
    kind: str = (
        "text"  # "text" | "code" | "openapi_operation" | "openapi_schema" | "markdown_section"
    )
    language: str | None = None
    artifact_qualname: str | None = None
    parent_document_id: str | None = None


class DocumentParser(ABC):
    @property
    @abstractmethod
    def name(self) -> str:  # "markdown" | "python" | "openapi" | ...
        ...

    @abstractmethod
    def supports(self, file_path: Path) -> bool: ...

    @abstractmethod
    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult: ...


@dataclass
class GraphNode:
    node_id: str
    label: str  # "Document" | "Module" | "Class" | ...
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    from_id: str
    to_id: str
    rel_type: Literal["CONTAINS", "RELATES"]
    kind: str | None = None  # ArtifactLinkKind.value when rel_type == "RELATES"
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    chunks: list[Chunk]
    document: GraphNode
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
