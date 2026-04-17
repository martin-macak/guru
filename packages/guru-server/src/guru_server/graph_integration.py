"""guru-server <-> guru-graph glue.

Graph is strictly optional. Any failure — disabled, unreachable, unhealthy —
is swallowed by `graph_or_skip` so end users never see a graph error.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Any

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import KbUpsert

logger = logging.getLogger(__name__)

_logged_features: set[str] = set()


async def graph_or_skip(coro: Awaitable[Any], *, feature: str) -> Any | None:
    """Run the graph coroutine; return None if the graph is unavailable.

    Logs at most once per feature per process so log noise stays bounded.
    """
    try:
        return await coro
    except GraphUnavailable as e:
        if feature not in _logged_features:
            logger.info(
                "graph unavailable for %s: %s (subsequent errors silent)",
                feature,
                e,
            )
            _logged_features.add(feature)
        return None
    except Exception as e:
        logger.warning("graph call for %s raised: %s", feature, e)
        return None


async def register_self_kb(
    *,
    client: GraphClient | None,
    name: str,
    project_root: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Upsert this guru-server's KB node via the graph client.

    No-op if client is None (graph disabled). Silently degrades on failure.
    """
    if client is None:
        return
    req = KbUpsert(
        name=name,
        project_root=project_root,
        tags=tags or [],
        metadata=metadata or {},
    )
    await graph_or_skip(client.upsert_kb(req), feature="register_self_kb")


def build_graph_client_if_enabled(*, graph_enabled: bool) -> GraphClient | None:
    if not graph_enabled:
        return None
    return GraphClient(socket_path=None, auto_start=True)
