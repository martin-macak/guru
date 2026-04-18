"""Artifact-to-artifact typed-link service."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from guru_core.graph_types import ArtifactLink, ArtifactLinkCreate, ArtifactLinkKind

from ..backend.base import ArtifactOpsBackend


class EndpointNotFoundError(RuntimeError):
    """Raised when one of the link endpoints does not exist as an artifact."""


class RelatesService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None:
        self._backend = backend

    def create(self, req: ArtifactLinkCreate, *, author: str) -> ArtifactLink:
        for endpoint in (req.from_id, req.to_id):
            if self._backend.get_artifact(node_id=endpoint) is None:
                raise EndpointNotFoundError(f"artifact {endpoint!r} not found")
        self._backend.create_relates_edge(
            from_id=req.from_id,
            to_id=req.to_id,
            kind=req.kind.value,
            properties={"author": author, "metadata_json": json.dumps(req.metadata)},
        )
        return ArtifactLink(
            from_id=req.from_id,
            to_id=req.to_id,
            kind=req.kind,
            created_at=datetime.now(UTC),
            author=author,
            metadata=req.metadata,
        )

    def delete(self, *, from_id: str, to_id: str, kind: ArtifactLinkKind) -> bool:
        return self._backend.delete_relates_edge(from_id=from_id, to_id=to_id, kind=kind.value)
