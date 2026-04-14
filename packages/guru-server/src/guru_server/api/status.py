from fastapi import APIRouter, Request

from guru_server.api.cache import _assemble_stats
from guru_server.api.models import StatusOut

router = APIRouter()


@router.get("/status", response_model=StatusOut)
async def get_status(request: Request):
    store = request.app.state.store
    registry = request.app.state.job_registry
    current = registry.current_job()
    cache_stats = None
    if getattr(request.app.state, "embed_cache", None) is not None:
        cache_stats = _assemble_stats(request)
    return StatusOut(
        server_running=True,
        document_count=store.document_count(),
        chunk_count=store.chunk_count(),
        last_indexed=request.app.state.last_indexed,
        ollama_available=True,
        model_loaded=True,
        current_job=current.to_summary() if current else None,
        cache=cache_stats,
    )
