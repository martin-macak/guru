"""In-memory GraphBackend for tests.

Deliberately does NOT parse Cypher. Exposes declarative helper methods used
by KbService tests; the Cypher escape-hatch path is only covered by real
Neo4j integration tests (@real_neo4j).
"""

from __future__ import annotations

import copy
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from guru_graph.backend.base import BackendHealth, BackendInfo, CypherResult, Tx
from guru_graph.versioning import check_migration_target


@dataclass
class _FakeLink:
    from_kb: str
    to_kb: str
    kind: str
    created_at: float
    metadata_json: str


@dataclass
class FakeBackend:
    """In-memory backend.

    Designed to support KbService unit tests without a JVM. Cypher methods
    are stubbed — tests that exercise Cypher should use real Neo4j.
    """

    _nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _links: list[_FakeLink] = field(default_factory=list)
    _started: bool = False
    _schema_version: int = 0

    # ---- Lifecycle ----
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

    # ---- Cypher surface (stubbed) ----
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

    # ---- Test helpers: declarative node/link ops (not Cypher) ----
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
                link.metadata_json = metadata_json  # idempotent update
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
