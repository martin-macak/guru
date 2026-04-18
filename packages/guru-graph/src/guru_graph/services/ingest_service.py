"""Reconciliation service: apply ParseResult payloads idempotently.

The service sits above :class:`ArtifactOpsBackend`. It expresses the
semantic contract:

  - Upsert document + sub-artifacts in the payload
  - Remove artifacts that disappeared between parses (via stored Document
    snapshot), orphaning any annotations targeting them
  - Replace outbound RELATES edges rooted at the document (they are
    recomputed from scratch each parse)

Orphan-preserving deletion: annotations targeting a deleted node have
their :ANNOTATES edge removed but the annotation node itself is preserved
for agent triage (:meth:`ArtifactOpsBackend.orphan_annotations_for`).
"""

from __future__ import annotations

import logging

from guru_core.graph_types import ParseResultPayload

from ..backend.base import ArtifactOpsBackend

logger = logging.getLogger(__name__)


class IngestService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None:
        self._backend = backend

    def submit(self, kb_name: str, payload: ParseResultPayload) -> None:
        """Reconcile a Document + its sub-artifacts to the graph.

        `kb_name` is currently carried for logging/future multi-tenancy
        checks; the document's node_id already encodes the kb (`{kb}::{rel_path}`).
        """
        doc_id = payload.document.node_id
        prev_ids = set(self._backend.get_document_snapshot(doc_id=doc_id))
        current_ids = {n.node_id for n in payload.nodes}

        # Step 1: compute victims (artifacts that disappeared) + their descendants
        to_delete_roots = list(prev_ids - current_ids)
        if to_delete_roots:
            all_victims: list[str] = []
            for nid in to_delete_roots:
                all_victims.extend(self._backend.delete_artifact_with_descendants(node_id=nid))
            if all_victims:
                # Orphan annotations BEFORE deleting, so the annotation
                # loses its :ANNOTATES edge but survives.
                self._backend.orphan_annotations_for(node_ids=all_victims)
                for nid in all_victims:
                    self._backend.delete_artifact(node_id=nid)

        # Step 2: upsert document + every sub-artifact
        self._backend.upsert_document(
            node_id=doc_id,
            label=payload.document.label,
            properties=payload.document.properties,
        )
        for n in payload.nodes:
            self._backend.upsert_artifact(
                node_id=n.node_id,
                label=n.label,
                properties=n.properties,
            )

        # Step 3: replace outbound RELATES rooted at this document
        self._backend.remove_outbound_relates_rooted_at(doc_id=doc_id)
        for e in payload.edges:
            if e.rel_type == "CONTAINS":
                self._backend.create_contains_edge(from_id=e.from_id, to_id=e.to_id)
            else:  # "RELATES"
                assert e.kind is not None  # Pydantic validator ensures this
                self._backend.create_relates_edge(
                    from_id=e.from_id,
                    to_id=e.to_id,
                    kind=e.kind,
                    properties=e.properties,
                )

        # Step 4: record new snapshot (sorted for deterministic order)
        self._backend.set_document_snapshot(doc_id=doc_id, node_ids=sorted(current_ids))

    def delete_document(self, kb_name: str, doc_id: str) -> None:
        """Remove a document and its entire CONTAINS subtree.

        Annotations targeting any deleted node are orphaned (target_id → None).
        Safe to call on a non-existent document (no-op).
        """
        victims = self._backend.delete_artifact_with_descendants(node_id=doc_id)
        if not victims:
            return
        self._backend.orphan_annotations_for(node_ids=victims)
        for nid in victims:
            self._backend.delete_artifact(node_id=nid)
