from guru_server.jobs import JobRegistry


def test_create_job():
    registry = JobRegistry()
    job = registry.create_job()
    assert job.status == "queued"
    assert job.job_type == "index"
    assert job.phase is None
    assert job.files_total == 0
    assert job.files_processed == 0
    assert job.files_skipped == 0
    assert job.files_deleted == 0
    assert job.chunks_created == 0
    assert job.error is None
    assert job.created_at is not None
    assert job.started_at is None
    assert job.finished_at is None


def test_get_job():
    registry = JobRegistry()
    job = registry.create_job()
    found = registry.get_job(job.job_id)
    assert found is job


def test_get_job_not_found():
    registry = JobRegistry()
    assert registry.get_job("nonexistent") is None


def test_current_job_none_when_idle():
    registry = JobRegistry()
    assert registry.current_job() is None


def test_current_job_returns_running():
    registry = JobRegistry()
    job = registry.create_job()
    job.status = "running"
    assert registry.current_job() is job


def test_current_job_returns_queued():
    registry = JobRegistry()
    job = registry.create_job()
    assert job.status == "queued"
    assert registry.current_job() is job


def test_current_job_ignores_completed():
    registry = JobRegistry()
    job = registry.create_job()
    job.status = "completed"
    assert registry.current_job() is None


def test_list_jobs():
    registry = JobRegistry()
    j1 = registry.create_job()
    j2 = registry.create_job()
    jobs = registry.list_jobs()
    assert len(jobs) == 2
    assert j1 in jobs
    assert j2 in jobs


def test_job_to_summary():
    registry = JobRegistry()
    job = registry.create_job()
    job.status = "running"
    job.phase = "indexing"
    job.files_total = 10
    job.files_processed = 3
    job.files_skipped = 2
    summary = job.to_summary()
    assert summary.job_id == job.job_id
    assert summary.status == "running"
    assert summary.phase == "indexing"
    assert summary.files_total == 10
    assert summary.files_processed == 3
    assert summary.files_skipped == 2


def test_job_to_detail():
    registry = JobRegistry()
    job = registry.create_job()
    job.status = "completed"
    job.files_total = 10
    job.files_processed = 8
    job.files_skipped = 2
    job.files_deleted = 1
    job.chunks_created = 40
    detail = job.to_detail()
    assert detail.job_id == job.job_id
    assert detail.job_type == "index"
    assert detail.status == "completed"
    assert detail.files_total == 10
    assert detail.chunks_created == 40
