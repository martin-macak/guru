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
from guru_core.graph_types import GraphEdgePayload, GraphNodePayload, KbUpsert, ParseResultPayload
from guru_server.ingestion.base import ParseResult

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


def parse_result_to_payload(pr: ParseResult) -> ParseResultPayload:
    """Convert a parser's internal ParseResult into the Pydantic wire payload.

    The server-side dataclasses (`GraphNode`, `GraphEdge`, `ParseResult`)
    live in `guru_server.ingestion.base` — parsers should not depend on
    Pydantic. This helper is the single conversion point to the wire schema
    consumed by `/ingest/parse-result`.
    """
    return ParseResultPayload(
        chunks_count=len(pr.chunks),
        document=GraphNodePayload(
            node_id=pr.document.node_id,
            label=pr.document.label,
            properties=pr.document.properties,
        ),
        nodes=[
            GraphNodePayload(node_id=n.node_id, label=n.label, properties=n.properties)
            for n in pr.nodes
        ],
        edges=[
            GraphEdgePayload(
                from_id=e.from_id,
                to_id=e.to_id,
                rel_type=e.rel_type,
                kind=e.kind,
                properties=e.properties,
            )
            for e in pr.edges
        ],
    )
