"""Domain services that translate KB operations into backend calls.

The backend exposes Cypher; this layer expresses business meaning. Swapping
backends = reimplement backend only, no change here.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Literal

from guru_core.graph_types import KbLink, KbLinkCreate, KbNode, KbUpsert, LinkKind

from ..backend.base import KbOpsBackend

logger = logging.getLogger(__name__)


class KbNotFoundError(RuntimeError):
    """Raised when a link endpoint does not exist."""


def _to_node(row: dict) -> KbNode:
    now = datetime.fromtimestamp(row["created_at"], tz=UTC)
    upd = datetime.fromtimestamp(row["updated_at"], tz=UTC)
    return KbNode(
        name=row["name"],
        project_root=row["project_root"],
        created_at=now,
        updated_at=upd,
        last_seen_at=None,
        tags=list(row.get("tags") or []),
        metadata=json.loads(row.get("metadata_json") or "{}"),
    )


def _to_link(row: dict) -> KbLink:
    created = datetime.fromtimestamp(row["created_at"], tz=UTC)
    return KbLink(
        from_kb=row["from_kb"],
        to_kb=row["to_kb"],
        kind=LinkKind(row["kind"]),
        created_at=created,
        metadata=json.loads(row.get("metadata_json") or "{}"),
    )


class KbService:
    """KB CRUD + KB-to-KB links.

    Both FakeBackend and Neo4jBackend provide `upsert_kb`/`get_kb`/`list_kbs`/
    `delete_kb`/`link`/`unlink`/`list_links_for` declarative methods to
    support this service without the service knowing about Cypher.
    """

    def __init__(self, *, backend: KbOpsBackend):
        self._backend = backend

    def upsert(self, req: KbUpsert) -> KbNode:
        self._backend.upsert_kb(
            name=req.name,
            project_root=req.project_root,
            tags=req.tags,
            metadata_json=json.dumps(req.metadata or {}),
        )
        row = self._backend.get_kb(req.name)
        assert row is not None
        return _to_node(row)

    def get(self, name: str) -> KbNode | None:
        row = self._backend.get_kb(name)
        return _to_node(row) if row else None

    def list(self, *, prefix: str | None = None, tag: str | None = None) -> list[KbNode]:
        rows = self._backend.list_kbs(prefix=prefix, tag=tag)
        return [_to_node(r) for r in rows]

    def delete(self, name: str) -> bool:
        return self._backend.delete_kb(name)

    def link(self, *, from_kb: str, req: KbLinkCreate) -> KbLink:
        if self._backend.get_kb(from_kb) is None:
            raise KbNotFoundError(f"from_kb {from_kb!r} does not exist")
        if self._backend.get_kb(req.to_kb) is None:
            raise KbNotFoundError(f"to_kb {req.to_kb!r} does not exist")
        self._backend.link(
            from_kb=from_kb,
            to_kb=req.to_kb,
            kind=req.kind.value,
            metadata_json=json.dumps(req.metadata or {}),
        )
        for row in self._backend.list_links_for(name=from_kb, direction="out"):
            if row["to_kb"] == req.to_kb and row["kind"] == req.kind.value:
                return _to_link(row)
        raise RuntimeError("link not found after create")

    def unlink(self, *, from_kb: str, to_kb: str, kind: LinkKind) -> bool:
        return self._backend.unlink(from_kb=from_kb, to_kb=to_kb, kind=kind.value)

    def list_links(
        self,
        *,
        name: str,
        direction: Literal["in", "out", "both"] = "both",
    ) -> list[KbLink]:
        rows = self._backend.list_links_for(name=name, direction=direction)
        return [_to_link(r) for r in rows]
