from __future__ import annotations

from fastapi import APIRouter, Request

from guru_core.types import (
    CacheDeleteResult,
    CachePruneRequest,
    CacheStatsOut,
)

router = APIRouter()


def _assemble_stats(request: Request) -> CacheStatsOut:
    cache = request.app.state.embed_cache
    registry = request.app.state.job_registry

    if cache is None:
        return CacheStatsOut(
            path="",
            total_entries=0,
            total_bytes=0,
            by_model={},
        )

    stats = cache.stats()

    # Find the most recent completed job for last_job_* fields
    last_hits = None
    last_misses = None
    last_rate = None
    completed = [j for j in registry.list_jobs() if j.status == "completed"]
    if completed:
        latest = max(completed, key=lambda j: j.finished_at or j.created_at)
        last_hits = latest.cache_hits
        last_misses = latest.cache_misses
        total = last_hits + last_misses
        last_rate = (last_hits / total) if total > 0 else None

    return CacheStatsOut(
        path=stats.path,
        total_entries=stats.total_entries,
        total_bytes=stats.total_bytes,
        by_model=stats.by_model,
        last_job_hits=last_hits,
        last_job_misses=last_misses,
        last_job_hit_rate=last_rate,
    )


@router.get("/cache", response_model=CacheStatsOut)
async def get_cache_stats(request: Request):
    return _assemble_stats(request)


@router.delete("/cache", response_model=CacheDeleteResult)
async def delete_cache_entries(request: Request, model: str | None = None):
    cache = request.app.state.embed_cache
    if cache is None:
        return CacheDeleteResult(deleted=0)
    deleted = cache.clear(model=model)
    return CacheDeleteResult(deleted=deleted)


@router.post("/cache/prune", response_model=CacheDeleteResult)
async def prune_cache_entries(request: Request, req: CachePruneRequest):
    cache = request.app.state.embed_cache
    if cache is None:
        return CacheDeleteResult(deleted=0)
    deleted = cache.prune(older_than_ms=req.older_than_ms)
    return CacheDeleteResult(deleted=deleted)
