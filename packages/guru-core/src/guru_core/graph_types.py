"""Shared Pydantic models for the graph plugin.

Per ARCHITECTURE.md, guru-core is the canonical source of shared types. The
graph daemon (`guru-graph`) imports these; the graph client (`GraphClient`
in this package) does too.

LinkKind vocabulary is a closed enum in v1. Extending it is a MINOR protocol
bump; renaming or removing a value is a MAJOR bump.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LinkKind(str, Enum):
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
