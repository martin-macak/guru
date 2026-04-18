"""Backend abstraction. See spec §Interface design.

The backend exposes Cypher execution + transactions. Domain operations
(upsert KB, link KBs, etc.) live in the service layer above and translate
to Cypher strings — so any openCypher backend can be swapped in by
implementing this Protocol.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

# Labels that `upsert_artifact` accepts. `Document` is intentionally excluded —
# documents go through `upsert_document`. Kept in sync with the m0002 schema.
ALLOWED_ARTIFACT_LABELS: frozenset[str] = frozenset(
    {
        "Module",
        "Class",
        "Function",
        "Method",
        "OpenApiSpec",
        "OpenApiOperation",
        "OpenApiSchema",
        "MarkdownSection",
    }
)


@dataclass(frozen=True)
class BackendInfo:
    name: str
    version: str
    schema_version: int


@dataclass(frozen=True)
class BackendHealth:
    healthy: bool
    detail: str = ""


@dataclass
class CypherResult:
    columns: list[str]
    rows: list[list[Any]]
    elapsed_ms: float = 0.0


@dataclass
class Tx:
    """Transaction handle. Backends may subclass if they need richer state."""

    backend: GraphBackend
    read_only: bool = False

    def execute(self, cypher: str, params: dict[str, Any] | None = None) -> CypherResult:
        if self.read_only:
            return self.backend.execute_read(cypher, params or {})
        return self.backend.execute(cypher, params or {})


@runtime_checkable
class GraphBackend(Protocol):
    """Backend-agnostic graph operations. Cypher-only surface."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def health(self) -> BackendHealth: ...
    def info(self) -> BackendInfo: ...
    def execute(self, cypher: str, params: dict[str, Any]) -> CypherResult: ...
    def execute_read(self, cypher: str, params: dict[str, Any]) -> CypherResult: ...

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[Tx]: ...

    def ensure_schema(self, target_version: int) -> None: ...


@runtime_checkable
class KbOpsBackend(GraphBackend, Protocol):
    """Extension of GraphBackend with declarative KB and link helpers.

    KbService is typed against this protocol so that static checkers and IDEs
    get full coverage of the declarative methods without polluting the
    Cypher-only GraphBackend surface.
    """

    def upsert_kb(
        self, *, name: str, project_root: str, tags: list[str], metadata_json: str
    ) -> None: ...
    def get_kb(self, name: str) -> dict[str, Any] | None: ...
    def list_kbs(
        self, *, prefix: str | None = None, tag: str | None = None
    ) -> list[dict[str, Any]]: ...
    def delete_kb(self, name: str) -> bool: ...
    def link(self, *, from_kb: str, to_kb: str, kind: str, metadata_json: str) -> None: ...
    def unlink(self, *, from_kb: str, to_kb: str, kind: str) -> bool: ...
    def list_links_for(self, *, name: str, direction: str = "both") -> list[dict[str, Any]]: ...


@runtime_checkable
class ArtifactOpsBackend(GraphBackend, Protocol):
    """Declarative artifact-graph operations.

    IngestService, ArtifactService, AnnotationService, and RelatesService
    are typed against this protocol. See m0002 schema in the design spec.
    """

    # ---- Ingest path ----
    def upsert_document(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None: ...

    def upsert_artifact(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None: ...

    def delete_artifact(self, *, node_id: str) -> None: ...

    def delete_artifact_with_descendants(self, *, node_id: str) -> list[str]:
        """Return the ids of `node_id` and all CONTAINS-descendants, without mutating the graph.

        Callers (typically :class:`IngestService`) use this to plan a delete:
        first collect the subtree, then orphan annotations targeting any node
        in the subtree, then call :meth:`delete_artifact` for each id. Order
        of the returned list is unspecified — sort if you need determinism.
        Returns an empty list if `node_id` is not present in the graph.
        """
        ...

    def create_contains_edge(self, *, from_id: str, to_id: str) -> None: ...

    def create_relates_edge(
        self, *, from_id: str, to_id: str, kind: str, properties: dict[str, Any]
    ) -> None: ...

    def delete_relates_edge(self, *, from_id: str, to_id: str, kind: str) -> bool: ...

    def remove_outbound_relates_rooted_at(self, *, doc_id: str) -> None: ...

    def get_document_snapshot(self, *, doc_id: str) -> list[str]: ...

    def set_document_snapshot(self, *, doc_id: str, node_ids: list[str]) -> None: ...

    def orphan_annotations_for(self, *, node_ids: list[str]) -> None: ...

    # ---- Artifact queries ----
    def get_artifact(self, *, node_id: str) -> dict[str, Any] | None: ...

    def list_neighbors(
        self,
        *,
        node_id: str,
        direction: Literal["in", "out", "both"],
        rel_type: Literal["CONTAINS", "RELATES", "both"],
        kind: str | None,
        depth: int,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def find_artifacts(
        self,
        *,
        name: str | None,
        qualname_prefix: str | None,
        label: str | None,
        tag: str | None,
        kb_name: str | None,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def list_annotations_for(self, *, node_id: str) -> list[dict[str, Any]]: ...

    def list_relates_for(self, *, node_id: str, direction: str) -> list[dict[str, Any]]: ...

    def list_artifact_neighbors(
        self,
        *,
        node_id: str,
        direction: str,
        rel_type: str,
        kind: str | None,
        depth: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...

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
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

    def delete_annotation(self, *, annotation_id: str) -> bool: ...

    def get_annotation(self, *, annotation_id: str) -> dict[str, Any] | None:
        """Return the annotation row by id, or None if not present.

        Row shape matches the other annotation-returning methods:
        `{annotation_id, target_id, target_label, kind, body, tags, author,
        created_at, updated_at, target_snapshot_json}`. `target_id` and
        `target_label` are None for orphaned annotations.
        """
        ...

    def list_orphans(self, *, limit: int) -> list[dict[str, Any]]: ...

    def reattach_orphan(self, *, annotation_id: str, new_target_id: str) -> bool: ...

class GraphBackendRegistry:
    """Registry for available GraphBackend implementations.

    Adding a backend later = one `register()` call + one class. Domain
    services / routes do not change.
    """

    _registry: ClassVar[dict[str, type]] = {}

    @classmethod
    def register(cls, name: str, backend_cls: type) -> None:
        cls._registry[name] = backend_cls

    @classmethod
    def get(cls, name: str) -> type:
        try:
            return cls._registry[name]
        except KeyError as e:
            raise KeyError(
                f"no backend registered for {name!r}. Known: {sorted(cls._registry)}"
            ) from e

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._registry)
