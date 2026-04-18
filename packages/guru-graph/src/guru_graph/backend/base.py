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
from typing import Any, ClassVar, Protocol, runtime_checkable


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
