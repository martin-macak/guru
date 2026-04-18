"""Annotation service: closed vocabulary (summary/gotcha/caveat/note) + open tags.

Sits above :class:`ArtifactOpsBackend`. Encodes the business semantics:
- SUMMARY annotations replace-in-place (one per target); other kinds append.
- Validates target existence before create; raises :class:`TargetNotFoundError`
  instead of bubbling backend-level errors.
- Builds a :class:`target_snapshot_json` capturing the target's label +
  breadcrumb-like display name, preserved even if the target is later deleted
  (so orphan triage has enough context to reattach or dismiss).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from guru_core.graph_types import AnnotationCreate, AnnotationKind, AnnotationNode

from ..backend.base import ArtifactOpsBackend


class TargetNotFoundError(RuntimeError):
    """Raised when an annotation references a node that does not exist."""


def _to_node(row: dict) -> AnnotationNode:
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


class AnnotationService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None:
        self._backend = backend

    def create(self, req: AnnotationCreate, *, author: str) -> AnnotationNode:
        target = self._backend.get_artifact(node_id=req.node_id)
        if target is None:
            raise TargetNotFoundError(f"target {req.node_id!r} not found")

        props = target["properties"]
        target_snapshot = json.dumps(
            {
                "target_id": req.node_id,
                "target_kind": target["label"],
                "breadcrumb": props.get("breadcrumb")
                or props.get("qualname")
                or props.get("name"),
            }
        )

        if req.kind == AnnotationKind.SUMMARY:
            # Reuse the existing summary's annotation_id if one exists so that
            # replace_summary_annotation can find and update it in-place.
            existing_summaries = [
                a
                for a in self._backend.list_annotations_for(node_id=req.node_id)
                if a["kind"] == "summary"
            ]
            annotation_id = (
                existing_summaries[0]["annotation_id"] if existing_summaries else str(uuid.uuid4())
            )
            row = self._backend.replace_summary_annotation(
                annotation_id=annotation_id,
                target_id=req.node_id,
                target_label=target["label"],
                body=req.body,
                tags=req.tags,
                author=author,
                target_snapshot_json=target_snapshot,
            )
        else:
            annotation_id = str(uuid.uuid4())
            row = self._backend.create_annotation(
                annotation_id=annotation_id,
                target_id=req.node_id,
                target_label=target["label"],
                kind=req.kind.value,
                body=req.body,
                tags=req.tags,
                author=author,
                target_snapshot_json=target_snapshot,
            )
        return _to_node(row)

    def delete(self, *, annotation_id: str) -> bool:
        return self._backend.delete_annotation(annotation_id=annotation_id)

    def list_orphans(self, *, limit: int = 50) -> list[dict]:
        return self._backend.list_orphans(limit=limit)

    def reattach(self, *, annotation_id: str, new_node_id: str) -> bool:
        target = self._backend.get_artifact(node_id=new_node_id)
        if target is None:
            raise TargetNotFoundError(f"new target {new_node_id!r} not found")
        return self._backend.reattach_orphan(
            annotation_id=annotation_id, new_target_id=new_node_id
        )
