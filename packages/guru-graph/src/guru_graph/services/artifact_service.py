"""Read-side artifact queries: describe, neighbors, find."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from guru_core.graph_types import (
    AnnotationKind,
    AnnotationNode,
    ArtifactFindQuery,
    ArtifactLink,
    ArtifactLinkKind,
    ArtifactNeighborsResult,
    ArtifactNode,
    GraphEdgePayload,
)

from ..backend.base import ArtifactOpsBackend


class ArtifactService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None:
        self._backend = backend

    def describe(self, *, node_id: str) -> ArtifactNode | None:
        art = self._backend.get_artifact(node_id=node_id)
        if art is None:
            return None
        return self._compose_node(art)

    def neighbors(
        self,
        *,
        node_id: str,
        direction: str,
        rel_type: str,
        kind: str | None,
        depth: int,
        limit: int,
    ) -> ArtifactNeighborsResult:
        rows = self._backend.list_neighbors(
            node_id=node_id,
            direction=direction,
            rel_type=rel_type,
            kind=kind,
            depth=depth,
            limit=limit,
        )
        nodes: list[ArtifactNode] = []
        edges: list[GraphEdgePayload] = []
        seen_ids: set[str] = set()
        for row in rows:
            neighbor_id = row["id"]
            if neighbor_id not in seen_ids:
                neighbor_art = self._backend.get_artifact(node_id=neighbor_id)
                if neighbor_art is not None:
                    nodes.append(self._compose_node(neighbor_art))
                    seen_ids.add(neighbor_id)
            # Build edge — direction in the row tells us which side is the source.
            # The backend returns (id, label, rel_type, kind, distance) without
            # explicit from/to. For an "out" walk, source=root, target=neighbor;
            # for "in", source=neighbor, target=root. For "both" we can't tell
            # from the row alone — emit one with the convention that we walked
            # outward. Reviewers may revisit.
            if direction == "in":
                edge_from, edge_to = neighbor_id, node_id
            else:
                edge_from, edge_to = node_id, neighbor_id
            edges.append(
                GraphEdgePayload(
                    from_id=edge_from,
                    to_id=edge_to,
                    rel_type=row["rel_type"],
                    kind=row["kind"],
                    properties={},
                )
            )
        return ArtifactNeighborsResult(node_id=node_id, nodes=nodes, edges=edges)

    def find(self, q: ArtifactFindQuery) -> list[ArtifactNode]:
        rows = self._backend.find_artifacts(
            name=q.name,
            qualname_prefix=q.qualname_prefix,
            label=q.label,
            tag=q.tag,
            kb_name=q.kb_name,
            limit=q.limit,
        )
        return [self._compose_node(r) for r in rows]

    def _compose_node(self, art: dict) -> ArtifactNode:
        node_id = art["id"]
        annotations = [
            _to_annotation_node(a) for a in self._backend.list_annotations_for(node_id=node_id)
        ]
        links_out = [
            _to_artifact_link(e)
            for e in self._backend.list_relates_for(node_id=node_id, direction="out")
        ]
        links_in = [
            _to_artifact_link(e)
            for e in self._backend.list_relates_for(node_id=node_id, direction="in")
        ]
        return ArtifactNode(
            id=node_id,
            label=art["label"],
            properties=art["properties"],
            annotations=annotations,
            links_out=links_out,
            links_in=links_in,
        )


def _to_annotation_node(row: dict) -> AnnotationNode:
    return AnnotationNode(
        id=row["annotation_id"],
        target_id=row.get("target_id"),
        target_label=row.get("target_label"),
        kind=AnnotationKind(row["kind"]),
        body=row["body"],
        tags=list(row.get("tags") or []),
        author=row["author"],
        created_at=datetime.fromtimestamp(row["created_at"], tz=UTC),
        updated_at=datetime.fromtimestamp(row["updated_at"], tz=UTC),
        target_snapshot_json=row["target_snapshot_json"],
    )


def _to_artifact_link(edge: dict) -> ArtifactLink:
    props = edge.get("properties") or {}
    metadata_json = props.get("metadata_json", "{}")
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return ArtifactLink(
        from_id=edge["from_id"],
        to_id=edge["to_id"],
        kind=ArtifactLinkKind(edge["kind"]),
        # FakeBackend / Neo4jBackend may not record per-edge created_at.
        # Use UTC now as a fallback — the wire schema requires *some* datetime.
        # If the backend ever surfaces a real timestamp, prefer that.
        created_at=datetime.fromtimestamp(props["created_at"], tz=UTC)
        if "created_at" in props
        else datetime.now(UTC),
        author=props.get("author"),
        metadata=metadata,
    )
