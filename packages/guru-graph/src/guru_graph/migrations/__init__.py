"""Forward-only migrations for the Neo4j schema.

Each migration is a callable taking the backend. It runs idempotent Cypher
and writes `(:_Meta {kind:'schema'}).schema_version` to its number. Applied
in order during `backend.ensure_schema(target)`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .m0001_initial import apply as m0001

logger = logging.getLogger(__name__)

Migration = Callable[[Any], None]

MIGRATIONS: list[tuple[int, Migration]] = [
    (1, m0001),
]


def run_pending_migrations(*, backend: Any, current: int, target: int) -> None:
    for version, fn in MIGRATIONS:
        if version <= current:
            continue
        if version > target:
            break
        logger.info("applying migration m%04d", version)
        fn(backend)
