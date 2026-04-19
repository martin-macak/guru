"""In-memory GraphBackend for tests.

Deliberately does NOT parse Cypher. Exposes declarative helper methods used
by service and route tests; the Cypher escape-hatch path is only covered by
real Neo4j integration tests (@real_neo4j).
"""

from __future__ import annotations

import copy
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from guru_graph.backend.base import (
    ALLOWED_ARTIFACT_LABELS,
    BackendHealth,
    BackendInfo,
    CypherResult,
    Tx,
)
from guru_graph.versioning import check_migration_target


@dataclass
class _FakeLink:
    from_kb: str
    to_kb: str
    kind: str
    created_at: float
    metadata_json: str


@dataclass
class _FakeArtifact:
    node_id: str
    label: str
    properties: dict[str, Any]
    snapshot_ids: list[str] = field(default_factory=list)


@dataclass
class _FakeEdge:
    from_id: str
    to_id: str
    rel_type: str
    kind: str | None
    properties: dict[str, Any]


@dataclass
class _FakeAnnotation:
    annotation_id: str
    target_id: str | None
    target_label: str | None
    kind: str
    body: str
    tags: list[str]
    author: str
    created_at: float
    updated_at: float
    target_snapshot_json: str


@dataclass
class FakeBackend:
    _nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _links: list[_FakeLink] = field(default_factory=list)
    _artifacts: dict[str, _FakeArtifact] = field(default_factory=dict)
    _edges: list[_FakeEdge] = field(default_factory=list)
    _annotations: dict[str, _FakeAnnotation] = field(default_factory=dict)
    # Keyed by (kb, doc_id)
    _document_nodes: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    _started: bool = False
    _schema_version: int = 0

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def health(self) -> BackendHealth:
        return BackendHealth(
            healthy=self._started,
            detail="" if self._started else "not started",
        )

    def info(self) -> BackendInfo:
        return BackendInfo(name="fake", version="0.0.0", schema_version=self._schema_version)

    def execute(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        return CypherResult(columns=[], rows=[], elapsed_ms=0.0)

    def execute_read(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        return CypherResult(columns=[], rows=[], elapsed_ms=0.0)

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[Tx]:
        yield Tx(backend=self, read_only=read_only)

    def ensure_schema(self, target_version: int) -> None:
        check_migration_target(current=self._schema_version, target=target_version)
        self._schema_version = target_version

    # ---- KB ops ----
    def upsert_kb(
        self, *, name: str, project_root: str, tags: list[str], metadata_json: str
    ) -> None:
        now = time.time()
        existing = self._nodes.get(name)
        created = existing["created_at"] if existing else now
        self._nodes[name] = {
            "name": name,
            "project_root": project_root,
            "tags": list(tags),
            "metadata_json": metadata_json,
            "created_at": created,
            "updated_at": now,
        }

    def get_kb(self, name: str) -> dict[str, Any] | None:
        node = self._nodes.get(name)
        return copy.deepcopy(node) if node else None

    def list_kbs(
        self, *, prefix: str | None = None, tag: str | None = None
    ) -> list[dict[str, Any]]:
        out = []
        for node in self._nodes.values():
            if prefix and not node["name"].startswith(prefix):
                continue
            if tag and tag not in node["tags"]:
                continue
            out.append(copy.deepcopy(node))
        return sorted(out, key=lambda n: n["name"])

    def delete_kb(self, name: str) -> bool:
        if name not in self._nodes:
            return False
        del self._nodes[name]
        self._links = [link for link in self._links if link.from_kb != name and link.to_kb != name]
        return True

    def link(self, *, from_kb: str, to_kb: str, kind: str, metadata_json: str) -> None:
        if from_kb not in self._nodes or to_kb not in self._nodes:
            raise KeyError(f"missing endpoint: {from_kb!r} or {to_kb!r}")
        for link in self._links:
            if link.from_kb == from_kb and link.to_kb == to_kb and link.kind == kind:
                link.metadata_json = metadata_json
                return
        self._links.append(
            _FakeLink(
                from_kb=from_kb,
                to_kb=to_kb,
                kind=kind,
                created_at=time.time(),
                metadata_json=metadata_json,
            )
        )

    def unlink(self, *, from_kb: str, to_kb: str, kind: str) -> bool:
        before = len(self._links)
        self._links = [
            link
            for link in self._links
            if not (link.from_kb == from_kb and link.to_kb == to_kb and link.kind == kind)
        ]
        return len(self._links) < before

    def list_links_for(self, *, name: str, direction: str = "both") -> list[dict[str, Any]]:
        out = []
        for link in self._links:
            include = (direction in ("out", "both") and link.from_kb == name) or (
                direction in ("in", "both") and link.to_kb == name
            )
            if include:
                out.append(
                    {
                        "from_kb": link.from_kb,
                        "to_kb": link.to_kb,
                        "kind": link.kind,
                        "created_at": link.created_at,
                        "metadata_json": link.metadata_json,
                    }
                )
        return out

    # ---- Artifact ingest ops ----
    def seed_artifact(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None:
        if label == "Document":
            self.upsert_document(node_id=node_id, label=label, properties=properties)
        else:
            self.upsert_artifact(node_id=node_id, label=label, properties=properties)

    def seed_artifact_edge(
        self,
        *,
        from_id: str,
        to_id: str,
        rel_type: str,
        kind: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        if rel_type == "CONTAINS":
            self.create_contains_edge(from_id=from_id, to_id=to_id)
            return
        if kind is None:
            raise ValueError("RELATES edge requires kind")
        self.create_relates_edge(
            from_id=from_id,
            to_id=to_id,
            kind=kind,
            properties=dict(properties or {}),
        )

    def upsert_document(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None:
        assert label == "Document", f"upsert_document requires label='Document', got {label!r}"
        existing = self._artifacts.get(node_id)
        snapshot = list(existing.snapshot_ids) if existing is not None else []
        self._artifacts[node_id] = _FakeArtifact(
            node_id=node_id,
            label=label,
            properties=dict(properties),
            snapshot_ids=snapshot,
        )

    def upsert_artifact(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None:
        if label != "Document" and label not in ALLOWED_ARTIFACT_LABELS:
            raise ValueError(f"unknown artifact label: {label!r}")
        existing = self._artifacts.get(node_id)
        snapshot = list(existing.snapshot_ids) if existing is not None else []
        self._artifacts[node_id] = _FakeArtifact(
            node_id=node_id,
            label=label,
            properties=dict(properties),
            snapshot_ids=snapshot,
        )

    def delete_artifact(self, *, node_id: str) -> None:
        self._artifacts.pop(node_id, None)
        self._edges = [e for e in self._edges if e.from_id != node_id and e.to_id != node_id]

    def delete_artifact_with_descendants(self, *, node_id: str) -> list[str]:
        if node_id not in self._artifacts:
            return []
        result = [node_id]
        seen = {node_id}
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            for edge in self._edges:
                if (
                    edge.rel_type == "CONTAINS"
                    and edge.from_id == current
                    and edge.to_id not in seen
                ):
                    seen.add(edge.to_id)
                    result.append(edge.to_id)
                    queue.append(edge.to_id)
        return result

    def create_contains_edge(self, *, from_id: str, to_id: str) -> None:
        for edge in self._edges:
            if edge.rel_type == "CONTAINS" and edge.from_id == from_id and edge.to_id == to_id:
                return
        self._edges.append(
            _FakeEdge(
                from_id=from_id,
                to_id=to_id,
                rel_type="CONTAINS",
                kind=None,
                properties={},
            )
        )

    def create_relates_edge(
        self, *, from_id: str, to_id: str, kind: str, properties: dict[str, Any]
    ) -> None:
        for edge in self._edges:
            if (
                edge.rel_type == "RELATES"
                and edge.from_id == from_id
                and edge.to_id == to_id
                and edge.kind == kind
            ):
                edge.properties = dict(properties)
                return
        self._edges.append(
            _FakeEdge(
                from_id=from_id,
                to_id=to_id,
                rel_type="RELATES",
                kind=kind,
                properties=dict(properties),
            )
        )

    def delete_relates_edge(self, *, from_id: str, to_id: str, kind: str) -> bool:
        before = len(self._edges)
        self._edges = [
            edge
            for edge in self._edges
            if not (
                edge.rel_type == "RELATES"
                and edge.from_id == from_id
                and edge.to_id == to_id
                and edge.kind == kind
            )
        ]
        return len(self._edges) < before

    def remove_outbound_relates_rooted_at(self, *, doc_id: str) -> None:
        reachable = {doc_id}
        queue = [doc_id]
        while queue:
            current = queue.pop(0)
            for edge in self._edges:
                if (
                    edge.rel_type == "CONTAINS"
                    and edge.from_id == current
                    and edge.to_id not in reachable
                ):
                    reachable.add(edge.to_id)
                    queue.append(edge.to_id)
        self._edges = [
            edge
            for edge in self._edges
            if not (edge.rel_type == "RELATES" and edge.from_id in reachable)
        ]

    def get_document_snapshot(self, *, doc_id: str) -> list[str]:
        art = self._artifacts.get(doc_id)
        return [] if art is None else list(art.snapshot_ids)

    def set_document_snapshot(self, *, doc_id: str, node_ids: list[str]) -> None:
        self._artifacts[doc_id].snapshot_ids = list(node_ids)

    def orphan_annotations_for(self, *, node_ids: list[str]) -> None:
        ids = set(node_ids)
        now = time.time()
        for ann in self._annotations.values():
            if ann.target_id in ids:
                ann.target_id = None
                ann.target_label = None
                ann.updated_at = now

    # ---- Artifact queries ----
    def get_artifact(self, node_id: str) -> dict[str, Any] | None:
        art = self._artifacts.get(node_id)
        if art is None:
            return None
        return {
            "id": art.node_id,
            "label": art.label,
            "properties": copy.deepcopy(art.properties),
        }

    def list_neighbors(
        self,
        *,
        node_id: str,
        direction: str,
        rel_type: str,
        kind: str | None,
        depth: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        if depth <= 0:
            depth = 1
        results: list[dict[str, Any]] = []
        visited = {node_id}
        frontier = [(node_id, 0)]
        while frontier and len(results) < limit:
            current, dist = frontier.pop(0)
            if dist >= depth:
                continue
            for edge in self._edges:
                if rel_type != "both" and edge.rel_type != rel_type:
                    continue
                if kind is not None and edge.rel_type == "RELATES" and edge.kind != kind:
                    continue
                neighbor_id: str | None = None
                if direction in ("out", "both") and edge.from_id == current:
                    neighbor_id = edge.to_id
                elif direction in ("in", "both") and edge.to_id == current:
                    neighbor_id = edge.from_id
                if neighbor_id is None or neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                art = self._artifacts.get(neighbor_id)
                results.append(
                    {
                        "id": neighbor_id,
                        "label": art.label if art else None,
                        "rel_type": edge.rel_type,
                        "kind": edge.kind,
                        "distance": dist + 1,
                    }
                )
                frontier.append((neighbor_id, dist + 1))
        return results

    def list_artifact_neighbors(
        self,
        *,
        node_id: str,
        direction: str,
        rel_type: str,
        kind: str | None,
        depth: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if node_id not in self._artifacts:
            return [], []
        visited = {node_id}
        ordered = [self.get_artifact(node_id=node_id)]
        frontier = [(node_id, 0)]
        edges_out: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str, str | None]] = set()
        while frontier and len(ordered) < limit:
            current_id, current_depth = frontier.pop(0)
            if current_depth >= depth:
                continue
            for edge in self._edges:
                if rel_type != "both" and edge.rel_type != rel_type:
                    continue
                if kind is not None and edge.rel_type == "RELATES" and edge.kind != kind:
                    continue
                matches_out = direction in ("out", "both") and edge.from_id == current_id
                matches_in = direction in ("in", "both") and edge.to_id == current_id
                if not matches_out and not matches_in:
                    continue
                key = (edge.from_id, edge.to_id, edge.rel_type, edge.kind)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges_out.append(
                        {
                            "from_id": edge.from_id,
                            "to_id": edge.to_id,
                            "rel_type": edge.rel_type,
                            "kind": edge.kind,
                            "properties": copy.deepcopy(edge.properties),
                        }
                    )
                next_id = edge.to_id if edge.from_id == current_id else edge.from_id
                if next_id not in visited and next_id in self._artifacts and len(ordered) < limit:
                    visited.add(next_id)
                    ordered.append(self.get_artifact(node_id=next_id))
                    frontier.append((next_id, current_depth + 1))
        return [row for row in ordered if row is not None], edges_out

    def find_artifacts(
        self,
        *,
        name: str | None,
        qualname_prefix: str | None,
        label: str | None,
        tag: str | None,
        kb_name: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for art in self._artifacts.values():
            if name is not None and not str(art.properties.get("name", "")).startswith(name):
                continue
            if qualname_prefix is not None and not str(
                art.properties.get("qualname", "")
            ).startswith(qualname_prefix):
                continue
            if label is not None and art.label != label:
                continue
            if tag is not None and tag not in (art.properties.get("tags") or []):
                continue
            if kb_name is not None and art.properties.get("kb_name") != kb_name:
                continue
            results.append(
                {
                    "id": art.node_id,
                    "label": art.label,
                    "properties": copy.deepcopy(art.properties),
                }
            )
            if len(results) >= limit:
                break
        return results

    def list_annotations_for(self, *, node_id: str) -> list[dict[str, Any]]:
        return [
            _annotation_to_dict(ann)
            for ann in self._annotations.values()
            if ann.target_id == node_id
        ]

    def list_relates_for(self, *, node_id: str, direction: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for edge in self._edges:
            if edge.rel_type != "RELATES":
                continue
            include = (direction in ("out", "both") and edge.from_id == node_id) or (
                direction in ("in", "both") and edge.to_id == node_id
            )
            if include:
                out.append(
                    {
                        "from_id": edge.from_id,
                        "to_id": edge.to_id,
                        "kind": edge.kind,
                        "properties": copy.deepcopy(edge.properties),
                    }
                )
        return out

    # ---- Annotations ----
    def create_annotation(
        self,
        *,
        annotation_id: str,
        target_id: str,
        target_label: str,
        kind: str,
        body: str,
        tags: list[str],
        author: str,
        target_snapshot_json: str,
    ) -> dict[str, Any]:
        if target_id not in self._artifacts:
            raise KeyError(f"target {target_id!r} not found")
        if annotation_id in self._annotations:
            raise ValueError(f"annotation {annotation_id!r} already exists")
        now = time.time()
        ann = _FakeAnnotation(
            annotation_id=annotation_id,
            target_id=target_id,
            target_label=target_label,
            kind=kind,
            body=body,
            tags=list(tags),
            author=author,
            created_at=now,
            updated_at=now,
            target_snapshot_json=target_snapshot_json,
        )
        self._annotations[annotation_id] = ann
        return _annotation_to_dict(ann)

    def replace_summary_annotation(
        self,
        *,
        annotation_id: str,
        target_id: str,
        target_label: str,
        body: str,
        tags: list[str],
        author: str,
        target_snapshot_json: str,
    ) -> dict[str, Any]:
        if target_id not in self._artifacts:
            raise KeyError(f"target {target_id!r} not found")
        now = time.time()
        existing = self._annotations.get(annotation_id)
        if existing is None:
            existing = _FakeAnnotation(
                annotation_id=annotation_id,
                target_id=target_id,
                target_label=target_label,
                kind="summary",
                body=body,
                tags=list(tags),
                author=author,
                created_at=now,
                updated_at=now,
                target_snapshot_json=target_snapshot_json,
            )
            self._annotations[annotation_id] = existing
            return _annotation_to_dict(existing)
        existing.target_id = target_id
        existing.target_label = target_label
        existing.kind = "summary"
        existing.body = body
        existing.tags = list(tags)
        existing.author = author
        existing.target_snapshot_json = target_snapshot_json
        existing.updated_at = now
        return _annotation_to_dict(existing)

    def delete_annotation(self, *, annotation_id: str) -> bool:
        if annotation_id not in self._annotations:
            return False
        del self._annotations[annotation_id]
        return True

    def get_annotation(self, *, annotation_id: str) -> dict[str, Any] | None:
        ann = self._annotations.get(annotation_id)
        return None if ann is None else _annotation_to_dict(ann)

    def list_orphans(self, *, limit: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for ann in self._annotations.values():
            if ann.target_id is None:
                out.append(_annotation_to_dict(ann))
                if len(out) >= limit:
                    break
        return out

    def reattach_orphan(self, *, annotation_id: str, new_target_id: str) -> bool:
        ann = self._annotations.get(annotation_id)
        if ann is None or ann.target_id is not None:
            return False
        target = self._artifacts.get(new_target_id)
        if target is None:
            return False
        ann.target_id = new_target_id
        ann.target_label = target.label
        ann.updated_at = time.time()
        return True

    # ---- Document node CRUD (sync layer) ----
    def list_document_nodes(self, kb: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(doc) for (k, _), doc in self._document_nodes.items() if k == kb]

    def upsert_document_node(self, kb: str, document: dict[str, Any]) -> None:
        key = (kb, document["id"])
        self._document_nodes[key] = {
            "id": document["id"],
            "title": document.get("title", ""),
            "path": document.get("path", ""),
        }

    def delete_document_node(self, kb: str, doc_id: str) -> None:
        self._document_nodes.pop((kb, doc_id), None)


def _annotation_to_dict(ann: _FakeAnnotation) -> dict[str, Any]:
    return {
        "annotation_id": ann.annotation_id,
        "target_id": ann.target_id,
        "target_label": ann.target_label,
        "kind": ann.kind,
        "body": ann.body,
        "tags": list(ann.tags),
        "author": ann.author,
        "created_at": ann.created_at,
        "updated_at": ann.updated_at,
        "target_snapshot_json": ann.target_snapshot_json,
    }
