from fastapi import APIRouter, HTTPException, Request

from guru_server.api.models import JobDetail

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, request: Request):
    registry = request.app.state.job_registry
    job = registry.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_detail()
