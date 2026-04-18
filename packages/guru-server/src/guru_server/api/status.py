from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from guru_core.graph_errors import GraphUnavailable
from guru_server.api.cache import _assemble_stats
from guru_server.api.models import StatusOut, WebRuntimeOut

router = APIRouter()

_GRAPH_HEALTH_TIMEOUT = 2.0  # seconds; keep /status fast even when graph is slow


@router.get("/status", response_model=StatusOut)
async def get_status(request: Request):
    store = request.app.state.store
    registry = request.app.state.job_registry
    current = registry.current_job()
    cache_stats = None
    if getattr(request.app.state, "embed_cache", None) is not None:
        cache_stats = _assemble_stats(request)

    graph_enabled = bool(getattr(request.app.state, "graph_enabled", False))
    graph_reachable = False
    client = getattr(request.app.state, "graph_client", None)
    if client is not None:
        try:
            h = await asyncio.wait_for(client.health(), timeout=_GRAPH_HEALTH_TIMEOUT)
            graph_reachable = bool(h.graph_reachable)
        except (GraphUnavailable, TimeoutError):
            graph_reachable = False
        except Exception:
            graph_reachable = False

    runtime = request.app.state.web_runtime

    return StatusOut(
        server_running=True,
        document_count=store.document_count(),
        chunk_count=store.chunk_count(),
        last_indexed=request.app.state.last_indexed,
        ollama_available=True,
        model_loaded=True,
        current_job=current.to_summary() if current else None,
        cache=cache_stats,
        graph_enabled=graph_enabled,
        graph_reachable=graph_reachable,
        web=WebRuntimeOut(
            enabled=runtime.enabled,
            available=runtime.available,
            url=runtime.url,
            reason=runtime.reason,
            auto_open=runtime.auto_open,
        ),
    )
