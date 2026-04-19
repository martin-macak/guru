from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from guru_core.client import GuruClient
from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.types import (
    DocumentListItem,
    DocumentOut,
    IndexAccepted,
    SearchResultOut,
    StatusResponse,
)

from .view_models import (
    DocumentDetailVM,
    GraphEdgeVM,
    GraphNodeVM,
    KnowledgeTreeItemVM,
    SearchHitVM,
    StatusSnapshotVM,
)


@runtime_checkable
class ArtifactGraphGateway(Protocol):
    async def neighbors(
        self, node_id: str, depth: int = 1
    ) -> tuple[list[GraphNodeVM], list[GraphEdgeVM]]: ...


@dataclass
class FakeArtifactGraphGateway:
    nodes: dict[str, GraphNodeVM] = field(default_factory=dict)
    edges: list[GraphEdgeVM] = field(default_factory=list)

    def seed(
        self,
        *,
        nodes: list[GraphNodeVM | dict[str, str]],
        edges: list[GraphEdgeVM | dict[str, str]],
    ) -> None:
        typed_nodes = [
            node if isinstance(node, GraphNodeVM) else GraphNodeVM(**node) for node in nodes
        ]
        typed_edges = [
            edge if isinstance(edge, GraphEdgeVM) else GraphEdgeVM(**edge) for edge in edges
        ]
        self.nodes = {node.node_id: node for node in typed_nodes}
        self.edges = typed_edges

    async def neighbors(
        self, node_id: str, depth: int = 1
    ) -> tuple[list[GraphNodeVM], list[GraphEdgeVM]]:
        if node_id not in self.nodes or depth < 1:
            return [], []

        visited = {node_id}
        ordered_nodes = [self.nodes[node_id]]
        frontier = deque([(node_id, 0)])
        selected_edges: list[GraphEdgeVM] = []
        seen_edges: set[tuple[str, str, str]] = set()

        while frontier:
            current_id, current_depth = frontier.popleft()
            if current_depth >= depth:
                continue
            for edge in self.edges:
                if edge.from_id == current_id or edge.to_id == current_id:
                    edge_key = (edge.from_id, edge.to_id, edge.rel_type)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        selected_edges.append(edge)
                    next_id = edge.to_id if edge.from_id == current_id else edge.from_id
                    if next_id not in visited and next_id in self.nodes:
                        visited.add(next_id)
                        ordered_nodes.append(self.nodes[next_id])
                        frontier.append((next_id, current_depth + 1))

        return ordered_nodes, selected_edges


@dataclass
class GraphClientArtifactGateway:
    client: GraphClient

    async def neighbors(
        self, node_id: str, depth: int = 1
    ) -> tuple[list[GraphNodeVM], list[GraphEdgeVM]]:
        payload = await self.client.neighbors(node_id, depth=depth)
        return (
            [
                GraphNodeVM(
                    node_id=node.id,
                    label=node.label,
                    kind=node.label,
                )
                for node in payload.nodes
            ],
            [
                GraphEdgeVM(
                    from_id=edge.from_id,
                    to_id=edge.to_id,
                    rel_type=edge.rel_type,
                )
                for edge in payload.edges
            ],
        )


class GuruSession:
    def __init__(
        self,
        *,
        guru_client: GuruClient,
        graph_client: GraphClient | None = None,
        artifact_gateway: ArtifactGraphGateway | None = None,
    ):
        self._guru = guru_client
        self._graph = graph_client
        self._artifact_gateway = artifact_gateway

    async def load_status(self) -> StatusSnapshotVM:
        raw = StatusResponse.model_validate(await self._guru.status())
        return StatusSnapshotVM(
            server_running=raw.server_running,
            document_count=raw.document_count,
            chunk_count=raw.chunk_count,
            graph_enabled=raw.graph_enabled,
            graph_reachable=raw.graph_reachable,
        )

    async def trigger_reindex(self) -> IndexAccepted:
        return IndexAccepted.model_validate(await self._guru.trigger_index())

    def can_run_graph_queries(self) -> bool:
        return self._graph is not None

    async def run_search(self, query: str) -> list[SearchHitVM]:
        raw_hits = await self._guru.search(query)
        return [
            SearchHitVM(
                file_path=typed_hit.file_path,
                title=typed_hit.header_breadcrumb,
                snippet=typed_hit.content,
                score=typed_hit.score,
                labels=typed_hit.labels,
                artifact_qualname=typed_hit.artifact_qualname,
            )
            for raw_hit in raw_hits
            for typed_hit in [SearchResultOut.model_validate(raw_hit)]
        ]

    async def load_documents(self) -> list[KnowledgeTreeItemVM]:
        raw_docs = await self._guru.list_documents()
        return [
            KnowledgeTreeItemVM(
                node_id=typed_doc.file_path,
                label=typed_doc.file_path,
                kind="document",
            )
            for raw_doc in raw_docs
            for typed_doc in [DocumentListItem.model_validate(raw_doc)]
        ]

    async def load_document(self, file_path: str) -> DocumentDetailVM:
        raw = DocumentOut.model_validate(await self._guru.get_document(file_path))
        return DocumentDetailVM(
            file_path=raw.file_path,
            content=raw.content,
            labels=list(raw.labels),
        )

    async def run_query(self, cypher: str) -> tuple[list[str], list[list[object]], float]:
        if self._graph is None:
            return [], [], 0.0
        result = await self._graph.query(cypher=cypher, read_only=True)
        return result.columns, result.rows, result.elapsed_ms

    async def load_graph_neighbors(
        self, node_id: str, depth: int = 1
    ) -> tuple[list[GraphNodeVM], list[GraphEdgeVM]]:
        if not node_id:
            return [], []
        gateway = self._artifact_gateway
        if gateway is None and self._graph is not None:
            gateway = GraphClientArtifactGateway(self._graph)
        if gateway is None:
            return [], []
        try:
            return await gateway.neighbors(node_id, depth=depth)
        except GraphUnavailable:
            return [], []
