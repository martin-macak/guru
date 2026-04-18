"""Shared Pydantic models for the graph plugin.

Per ARCHITECTURE.md, guru-core is the canonical source of shared types. The
graph daemon (`guru-graph`) imports these; the graph client (`GraphClient`
in this package) does too.

LinkKind vocabulary is a closed enum in v1. Extending it is a MINOR protocol
bump; renaming or removing a value is a MAJOR bump.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LinkKind(StrEnum):
    """Controlled vocabulary for KB-to-KB relationship kinds.

    Each value is documented below. The vocabulary is closed in protocol v1;
    new kinds are additive (MINOR bump). Rename/remove = MAJOR bump.
    """

    # Source KB relies on target KB at runtime or build time
    # (library, service, module dependency).
    DEPENDS_ON = "depends_on"

    # Source KB was forked / derived from target KB's code history.
    FORK_OF = "fork_of"

    # Source KB references target KB textually or semantically, without a
    # hard dependency (docs, design notes, changelog).
    REFERENCES = "references"

    # Generic lightweight association; use sparingly when no stronger kind
    # applies.
    RELATED_TO = "related_to"

    # Source KB is a functional or code-level mirror of target
    # (vendored copy, cross-language port).
    MIRRORS = "mirrors"


class KbUpsert(BaseModel):
    """Request body for POST /kbs (also used as input to GraphClient.upsert_kb)."""

    model_config = ConfigDict(extra="ignore")
    name: str
    project_root: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KbNode(BaseModel):
    """A KB node in the graph. Persistent across server restarts.

    `last_seen_at` is hydrated at query time from federation liveness; a
    null value means the KB has never been seen live (or liveness data was
    unavailable).
    """

    model_config = ConfigDict(extra="ignore")
    name: str
    project_root: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KbLinkCreate(BaseModel):
    """Request body for POST /kbs/{name}/links."""

    model_config = ConfigDict(extra="ignore")
    to_kb: str
    kind: LinkKind
    metadata: dict[str, Any] = Field(default_factory=dict)


class KbLink(BaseModel):
    """A directed KB-to-KB link."""

    model_config = ConfigDict(extra="ignore")
    from_kb: str
    to_kb: str
    kind: LinkKind
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class CypherQuery(BaseModel):
    """Request body for POST /query — the Cypher escape hatch.

    read_only routes through the backend's read-only execution path. We do
    NOT parse Cypher to detect reads; the driver enforces it.
    """

    model_config = ConfigDict(extra="ignore")
    cypher: str
    params: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    elapsed_ms: float


class Health(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    graph_reachable: bool
    backend: str
    backend_version: str
    schema_version: int


class VersionInfo(BaseModel):
    protocol_version: str
    backend: str
    backend_version: str
    schema_version: int


# ---------------------------------------------------------------------------
# Artifact-graph types (intra-KB RELATES-edge vocabulary and wire schema)
# ---------------------------------------------------------------------------


class ArtifactLinkKind(StrEnum):
    """Closed vocabulary for intra-KB RELATES-edge kinds.

    These describe relationships between artifacts *within* a single knowledge
    base (e.g. file imports another file). They are distinct from `LinkKind`
    which describes KB-to-KB relationships.
    """

    IMPORTS = "imports"
    INHERITS_FROM = "inherits_from"
    IMPLEMENTS = "implements"
    CALLS = "calls"
    REFERENCES = "references"
    DOCUMENTS = "documents"


class AnnotationKind(StrEnum):
    """Closed vocabulary for human/AI annotations attached to graph nodes."""

    SUMMARY = "summary"
    GOTCHA = "gotcha"
    CAVEAT = "caveat"
    NOTE = "note"


class GraphNodePayload(BaseModel):
    """A single node in the artifact graph, as sent over the wire."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdgePayload(BaseModel):
    """A directed edge in the artifact graph, as sent over the wire.

    Invariant: a RELATES edge must carry a `kind`; a CONTAINS edge must not.
    """

    model_config = ConfigDict(extra="forbid")

    from_id: str
    to_id: str
    rel_type: Literal["CONTAINS", "RELATES"]
    kind: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _kind_consistent(cls, kind: str | None, info: Any) -> str | None:
        rel_type = info.data.get("rel_type")
        if rel_type == "RELATES" and kind is None:
            raise ValueError("kind must not be None when rel_type is 'RELATES'")
        if rel_type == "CONTAINS" and kind is not None:
            raise ValueError("kind must be None when rel_type is 'CONTAINS'")
        return kind


class ParseResultPayload(BaseModel):
    """Wire schema for POST /ingest/parse-result.

    The server's indexer converts its internal `ParseResult` to this model
    before POSTing to the graph daemon.
    """

    model_config = ConfigDict(extra="forbid")

    chunks_count: int
    document: GraphNodePayload
    nodes: list[GraphNodePayload] = Field(default_factory=list)
    edges: list[GraphEdgePayload] = Field(default_factory=list)


# --- Annotation types ---


class AnnotationCreate(BaseModel):
    """Request body for POST /annotations."""

    model_config = ConfigDict(extra="forbid")
    node_id: str
    kind: AnnotationKind
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class AnnotationNode(BaseModel):
    """Wire representation of an annotation returned by the graph daemon."""

    model_config = ConfigDict(extra="ignore")
    id: str
    target_id: str | None
    target_label: str | None
    kind: AnnotationKind
    body: str
    tags: list[str]
    author: str
    created_at: datetime
    updated_at: datetime
    target_snapshot_json: str


class OrphanAnnotation(BaseModel):
    """An annotation whose target node no longer exists in the graph."""

    model_config = ConfigDict(extra="ignore")
    id: str
    kind: AnnotationKind
    body: str
    tags: list[str]
    author: str
    created_at: datetime
    updated_at: datetime
    target_snapshot_json: str


class ReattachRequest(BaseModel):
    """Request body for POST /annotations/{id}/reattach."""

    model_config = ConfigDict(extra="forbid")
    new_node_id: str


# --- Artifact RELATES link types ---


class ArtifactLinkCreate(BaseModel):
    """Request body for POST /relates."""

    model_config = ConfigDict(extra="forbid")
    from_id: str
    to_id: str
    kind: ArtifactLinkKind
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactLink(BaseModel):
    """Wire representation of a RELATES edge returned by the graph daemon."""

    model_config = ConfigDict(extra="ignore")
    from_id: str
    to_id: str
    kind: ArtifactLinkKind
    created_at: datetime
    author: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactUnlink(BaseModel):
    """Request body for DELETE /relates."""

    model_config = ConfigDict(extra="forbid")
    from_id: str
    to_id: str
    kind: ArtifactLinkKind


class ArtifactNode(BaseModel):
    """Wire representation of an Artifact, with annotations and links inline."""

    model_config = ConfigDict(extra="ignore")
    id: str
    label: str
    properties: dict[str, Any]
    annotations: list[AnnotationNode] = Field(default_factory=list)
    links_out: list[ArtifactLink] = Field(default_factory=list)
    links_in: list[ArtifactLink] = Field(default_factory=list)


class ArtifactNeighborsResult(BaseModel):
    """Result of GET /artifacts/{id}/neighbors — nodes + the edges connecting them."""

    model_config = ConfigDict(extra="ignore")
    node_id: str
    nodes: list[ArtifactNode]
    edges: list[GraphEdgePayload]


class ArtifactFindQuery(BaseModel):
    """Request body for POST /artifacts/find."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    qualname_prefix: str | None = None
    label: str | None = None
    tag: str | None = None
    kb_name: str | None = None
    limit: int = 50
