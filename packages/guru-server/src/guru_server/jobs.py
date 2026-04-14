from __future__ import annotations

import uuid
from datetime import UTC, datetime

from guru_core.types import JobDetail, JobSummary


class Job:
    def __init__(self) -> None:
        self.job_id: str = str(uuid.uuid4())
        self.job_type: str = "index"
        self.status: str = "queued"
        self.phase: str | None = None
        self.files_total: int = 0
        self.files_processed: int = 0
        self.files_skipped: int = 0
        self.files_deleted: int = 0
        self.chunks_created: int = 0
        self.error: str | None = None
        self.created_at: datetime = datetime.now(UTC)
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    def to_summary(self) -> JobSummary:
        return JobSummary(
            job_id=self.job_id,
            status=self.status,
            phase=self.phase,
            files_total=self.files_total,
            files_processed=self.files_processed,
            files_skipped=self.files_skipped,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
        )

    def to_detail(self) -> JobDetail:
        return JobDetail(
            job_id=self.job_id,
            job_type=self.job_type,
            status=self.status,
            phase=self.phase,
            files_total=self.files_total,
            files_processed=self.files_processed,
            files_skipped=self.files_skipped,
            files_deleted=self.files_deleted,
            chunks_created=self.chunks_created,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            error=self.error,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
        )


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create_job(self) -> Job:
        job = Job()
        self._jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def current_job(self) -> Job | None:
        for job in self._jobs.values():
            if job.status in ("queued", "running"):
                return job
        return None

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())
