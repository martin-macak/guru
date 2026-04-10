import asyncio
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from guru_server.api.models import IndexAccepted

logger = logging.getLogger(__name__)

router = APIRouter()


class IndexBody(BaseModel):
    path: str | None = None


@router.post("/index", response_model=IndexAccepted)
async def trigger_index(body: IndexBody, request: Request):
    registry = request.app.state.job_registry

    # Concurrency guard: return existing job if one is active
    current = registry.current_job()
    if current is not None:
        return IndexAccepted(
            job_id=current.job_id,
            status=current.status,
            message="Indexing already in progress",
        )

    job = registry.create_job()
    logger.info(
        "Indexing requested (path=%s), job=%s", body.path or "project root", job.job_id[:8]
    )

    # Launch background indexing task — store task reference to prevent GC
    indexer = request.app.state.indexer
    if indexer is not None:
        _task = asyncio.create_task(indexer.run(job))  # noqa: RUF006

    return IndexAccepted(
        job_id=job.job_id,
        status=job.status,
        message="Indexing started",
    )
