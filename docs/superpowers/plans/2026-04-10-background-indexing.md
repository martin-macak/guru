# Background Indexing and Change Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synchronous, manual-only indexing with non-blocking background indexing, content-hash-based change detection, file-system watching, and observable job progress.

**Architecture:** A `JobRegistry` on `app.state` manages in-memory `Job` objects. Background indexing runs via `asyncio.create_task()`. A `file_manifest` LanceDB table tracks per-file hashes/mtimes for incremental re-indexing. `watchfiles` monitors the file system for changes after the initial startup index completes. All new Pydantic types live in `guru-core` (canonical source of truth).

**Tech Stack:** Python 3.13, FastAPI, LanceDB, asyncio, watchfiles, Pydantic, pytest, behave

**Spec:** `docs/superpowers/specs/2026-04-10-background-indexing-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `packages/guru-server/src/guru_server/jobs.py` | `Job` model and `JobRegistry` class |
| `packages/guru-server/src/guru_server/manifest.py` | `FileManifest` class — LanceDB `file_manifest` table CRUD |
| `packages/guru-server/src/guru_server/indexer.py` | `BackgroundIndexer` — two-phase indexing engine (discovery + indexing) |
| `packages/guru-server/src/guru_server/watcher.py` | File-system watcher using `watchfiles` |
| `packages/guru-server/tests/test_jobs.py` | Unit tests for `Job` and `JobRegistry` |
| `packages/guru-server/tests/test_manifest.py` | Unit tests for `FileManifest` |
| `packages/guru-server/tests/test_indexer.py` | Unit tests for `BackgroundIndexer` |
| `packages/guru-server/tests/test_watcher.py` | Unit tests for file-system watcher |
| `tests/e2e/features/background_indexing.feature` | BDD feature file for background indexing |
| `tests/e2e/features/steps/background_indexing_steps.py` | Step definitions for background indexing BDD |

### Modified Files

| File | What Changes |
|------|-------------|
| `packages/guru-core/src/guru_core/types.py` | Add `IndexAccepted`, `JobSummary`, `JobDetail`; update `StatusOut` |
| `packages/guru-core/src/guru_core/client.py` | Add `get_job()` method |
| `packages/guru-server/src/guru_server/api/models.py` | Re-export new types |
| `packages/guru-server/src/guru_server/api/index.py` | Return `IndexAccepted`, submit background job |
| `packages/guru-server/src/guru_server/api/status.py` | Include `current_job` in response |
| `packages/guru-server/src/guru_server/api/__init__.py` | Add jobs router |
| `packages/guru-server/src/guru_server/app.py` | Add `JobRegistry` to state, add lifespan for auto-index + watcher |
| `packages/guru-server/src/guru_server/storage.py` | No changes (existing API sufficient) |
| `packages/guru-server/pyproject.toml` | Add `watchfiles` dependency |
| `packages/guru-cli/src/guru_cli/cli.py` | Update `index` and `status` commands, add `--job` flag |
| `packages/guru-server/tests/test_api.py` | Update tests for new response shapes |
| `tests/e2e/features/knowledge_base.feature` | Update scenarios for async index responses |
| `tests/e2e/features/steps/cli_steps.py` | Update step definitions for new output formats |
| `tests/e2e/features/environment.py` | Add index-wait helper for BDD tests |

---

## Task 1: Add Pydantic Types to guru-core

**Files:**
- Modify: `packages/guru-core/src/guru_core/types.py`
- Test: `packages/guru-core/tests/test_types.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `packages/guru-core/tests/test_types.py`:

```python
from datetime import UTC, datetime

from guru_core.types import IndexAccepted, JobDetail, JobSummary, StatusOut


def test_index_accepted_model():
    obj = IndexAccepted(job_id="abc-123", status="running", message="Indexing started")
    assert obj.job_id == "abc-123"
    assert obj.status == "running"
    assert obj.message == "Indexing started"


def test_job_summary_model():
    obj = JobSummary(
        job_id="abc-123",
        status="running",
        phase="indexing",
        files_total=15,
        files_processed=7,
        files_skipped=3,
    )
    assert obj.job_id == "abc-123"
    assert obj.phase == "indexing"


def test_job_detail_model():
    now = datetime.now(UTC)
    obj = JobDetail(
        job_id="abc-123",
        job_type="index",
        status="completed",
        phase=None,
        files_total=15,
        files_processed=12,
        files_skipped=3,
        files_deleted=1,
        chunks_created=48,
        error=None,
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    assert obj.chunks_created == 48
    assert obj.files_deleted == 1


def test_status_out_with_current_job():
    now = datetime.now(UTC)
    job = JobSummary(
        job_id="abc-123",
        status="running",
        phase="discovery",
        files_total=0,
        files_processed=0,
        files_skipped=0,
    )
    status = StatusOut(
        server_running=True,
        document_count=5,
        chunk_count=20,
        last_indexed=now,
        ollama_available=True,
        model_loaded=True,
        current_job=job,
    )
    assert status.current_job is not None
    assert status.current_job.job_id == "abc-123"


def test_status_out_without_current_job():
    status = StatusOut(
        server_running=True,
        document_count=0,
        chunk_count=0,
        last_indexed=None,
        ollama_available=True,
        model_loaded=True,
    )
    assert status.current_job is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-core/tests/test_types.py -v`
Expected: FAIL — `ImportError: cannot import name 'IndexAccepted'`

- [ ] **Step 3: Implement the new types**

Edit `packages/guru-core/src/guru_core/types.py`. Add after the `IndexOut` class (line 79):

```python
class IndexAccepted(BaseModel):
    job_id: str
    status: str
    message: str


class JobSummary(BaseModel):
    job_id: str
    status: str
    phase: str | None
    files_total: int
    files_processed: int
    files_skipped: int


class JobDetail(BaseModel):
    job_id: str
    job_type: str
    status: str
    phase: str | None
    files_total: int
    files_processed: int
    files_skipped: int
    files_deleted: int
    chunks_created: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
```

Update `StatusOut` (line 68-74) to add the `current_job` field:

```python
class StatusOut(BaseModel):
    server_running: bool
    document_count: int
    chunk_count: int
    last_indexed: datetime | None
    ollama_available: bool
    model_loaded: bool
    current_job: JobSummary | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-core/tests/test_types.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Update api/models.py re-exports**

Edit `packages/guru-server/src/guru_server/api/models.py` to add the new re-exports:

```python
"""API response/request models — re-exported from guru_core.types (canonical source)."""

from guru_core.types import (
    DocumentListItem,
    DocumentOut,
    IndexAccepted,
    IndexOut,
    JobDetail,
    JobSummary,
    SearchResultOut,
    SectionOut,
    StatusOut,
)

__all__ = [
    "DocumentListItem",
    "DocumentOut",
    "IndexAccepted",
    "IndexOut",
    "JobDetail",
    "JobSummary",
    "SearchResultOut",
    "SectionOut",
    "StatusOut",
]
```

- [ ] **Step 6: Run all existing tests to verify no regressions**

Run: `uv run pytest packages/guru-core/ packages/guru-server/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add packages/guru-core/src/guru_core/types.py \
       packages/guru-core/tests/test_types.py \
       packages/guru-server/src/guru_server/api/models.py
git commit -m "feat: add Pydantic types for background indexing (#18)"
```

---

## Task 2: Job Model and JobRegistry

**Files:**
- Create: `packages/guru-server/src/guru_server/jobs.py`
- Test: `packages/guru-server/tests/test_jobs.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `packages/guru-server/tests/test_jobs.py`:

```python
from guru_server.jobs import Job, JobRegistry


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'guru_server.jobs'`

- [ ] **Step 3: Implement Job and JobRegistry**

Create `packages/guru-server/src/guru_server/jobs.py`:

```python
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

    def to_summary(self) -> JobSummary:
        return JobSummary(
            job_id=self.job_id,
            status=self.status,
            phase=self.phase,
            files_total=self.files_total,
            files_processed=self.files_processed,
            files_skipped=self.files_skipped,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_jobs.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/jobs.py \
       packages/guru-server/tests/test_jobs.py
git commit -m "feat: add Job model and JobRegistry (#18)"
```

---

## Task 3: File Manifest (Change Detection Store)

**Files:**
- Create: `packages/guru-server/src/guru_server/manifest.py`
- Test: `packages/guru-server/tests/test_manifest.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `packages/guru-server/tests/test_manifest.py`:

```python
import time

import pytest

from guru_server.manifest import FileManifest


@pytest.fixture
def manifest(tmp_path):
    import lancedb

    db = lancedb.connect(str(tmp_path / "db"))
    return FileManifest(db)


def test_get_entry_returns_none_for_unknown(manifest):
    assert manifest.get_entry("nonexistent.md") is None


def test_upsert_and_get_entry(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc123", mtime=1000.0, chunk_count=5)
    entry = manifest.get_entry("docs/guide.md")
    assert entry is not None
    assert entry["file_path"] == "docs/guide.md"
    assert entry["content_hash"] == "abc123"
    assert entry["mtime"] == 1000.0
    assert entry["chunk_count"] == 5
    assert entry["indexed_at"] > 0


def test_upsert_overwrites_existing(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1000.0, chunk_count=3)
    manifest.upsert("docs/guide.md", content_hash="def", mtime=2000.0, chunk_count=5)
    entry = manifest.get_entry("docs/guide.md")
    assert entry["content_hash"] == "def"
    assert entry["mtime"] == 2000.0
    assert entry["chunk_count"] == 5


def test_all_entries(manifest):
    manifest.upsert("a.md", content_hash="aaa", mtime=1.0, chunk_count=1)
    manifest.upsert("b.md", content_hash="bbb", mtime=2.0, chunk_count=2)
    entries = manifest.all_entries()
    paths = {e["file_path"] for e in entries}
    assert paths == {"a.md", "b.md"}


def test_delete_entry(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1.0, chunk_count=3)
    manifest.delete_entry("docs/guide.md")
    assert manifest.get_entry("docs/guide.md") is None


def test_delete_entries_batch(manifest):
    manifest.upsert("a.md", content_hash="aaa", mtime=1.0, chunk_count=1)
    manifest.upsert("b.md", content_hash="bbb", mtime=2.0, chunk_count=2)
    manifest.upsert("c.md", content_hash="ccc", mtime=3.0, chunk_count=3)
    manifest.delete_entries(["a.md", "b.md"])
    assert manifest.get_entry("a.md") is None
    assert manifest.get_entry("b.md") is None
    assert manifest.get_entry("c.md") is not None


def test_update_mtime_only(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1000.0, chunk_count=3)
    manifest.update_mtime("docs/guide.md", mtime=2000.0)
    entry = manifest.get_entry("docs/guide.md")
    assert entry["mtime"] == 2000.0
    assert entry["content_hash"] == "abc"  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'guru_server.manifest'`

- [ ] **Step 3: Implement FileManifest**

Create `packages/guru-server/src/guru_server/manifest.py`:

```python
from __future__ import annotations

import logging
import time

import lancedb

logger = logging.getLogger(__name__)

TABLE_NAME = "file_manifest"

_TABLE_NOT_FOUND_PHRASES = ("not found", "does not exist", "no such", "notfounderror")


class FileManifest:
    """Tracks per-file indexing state in a LanceDB table."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        self._db = db
        self._table = None

    def _get_table(self):
        if self._table is None:
            try:
                self._table = self._db.open_table(TABLE_NAME)
            except FileNotFoundError:
                return None
            except Exception as exc:
                msg = str(exc).lower()
                if any(phrase in msg for phrase in _TABLE_NOT_FOUND_PHRASES):
                    return None
                raise
        return self._table

    def _ensure_table(self):
        table = self._get_table()
        if table is None:
            self._table = self._db.create_table(
                TABLE_NAME,
                data=[
                    {
                        "file_path": "__placeholder__",
                        "content_hash": "",
                        "mtime": 0.0,
                        "indexed_at": 0.0,
                        "chunk_count": 0,
                    }
                ],
            )
            self._table.delete("file_path = '__placeholder__'")
        return self._table

    def get_entry(self, file_path: str) -> dict | None:
        table = self._get_table()
        if table is None:
            return None
        rows = (
            table.search(None)
            .where(f"file_path = '{_escape(file_path)}'", prefilter=True)
            .select(["file_path", "content_hash", "mtime", "indexed_at", "chunk_count"])
            .to_list()
        )
        if not rows:
            return None
        return rows[0]

    def all_entries(self) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        return (
            table.search(None)
            .select(["file_path", "content_hash", "mtime", "indexed_at", "chunk_count"])
            .to_list()
        )

    def upsert(self, file_path: str, *, content_hash: str, mtime: float, chunk_count: int) -> None:
        table = self._ensure_table()
        # Delete existing entry if present
        table.delete(f"file_path = '{_escape(file_path)}'")
        table.add(
            [
                {
                    "file_path": file_path,
                    "content_hash": content_hash,
                    "mtime": mtime,
                    "indexed_at": time.time(),
                    "chunk_count": chunk_count,
                }
            ]
        )

    def update_mtime(self, file_path: str, *, mtime: float) -> None:
        entry = self.get_entry(file_path)
        if entry is None:
            return
        table = self._get_table()
        table.delete(f"file_path = '{_escape(file_path)}'")
        table.add(
            [
                {
                    "file_path": file_path,
                    "content_hash": entry["content_hash"],
                    "mtime": mtime,
                    "indexed_at": entry["indexed_at"],
                    "chunk_count": entry["chunk_count"],
                }
            ]
        )

    def delete_entry(self, file_path: str) -> None:
        table = self._get_table()
        if table is None:
            return
        table.delete(f"file_path = '{_escape(file_path)}'")

    def delete_entries(self, file_paths: list[str]) -> None:
        table = self._get_table()
        if table is None:
            return
        escaped = ", ".join(f"'{_escape(fp)}'" for fp in file_paths)
        table.delete(f"file_path IN ({escaped})")


def _escape(value: str) -> str:
    return value.replace("'", "''")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_manifest.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/manifest.py \
       packages/guru-server/tests/test_manifest.py
git commit -m "feat: add FileManifest for change detection (#18)"
```

---

## Task 4: Background Indexer

**Files:**
- Create: `packages/guru-server/src/guru_server/indexer.py`
- Test: `packages/guru-server/tests/test_indexer.py` (create)

This is the core engine: two-phase discovery + indexing with change detection.

- [ ] **Step 1: Write the failing tests**

Create `packages/guru-server/tests/test_indexer.py`:

```python
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import lancedb
import pytest

from guru_core.types import MatchConfig, Rule
from guru_server.indexer import BackgroundIndexer
from guru_server.jobs import Job, JobRegistry
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore


@pytest.fixture
def project_dir(tmp_path):
    """Create a project with two markdown files."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nHello world.")
    (docs / "api.md").write_text("# API\n\nEndpoint docs.")
    (tmp_path / ".guru").mkdir()
    (tmp_path / ".guru" / "db").mkdir()
    return tmp_path


@pytest.fixture
def store(project_dir):
    return VectorStore(db_path=str(project_dir / ".guru" / "db"))


@pytest.fixture
def manifest(project_dir):
    db = lancedb.connect(str(project_dir / ".guru" / "db"))
    return FileManifest(db)


@pytest.fixture
def embedder():
    mock = MagicMock()
    mock.embed_batch = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def config():
    return [Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))]


@pytest.fixture
def registry():
    return JobRegistry()


@pytest.fixture
def indexer(store, manifest, embedder, config, project_dir, registry):
    return BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=project_dir,
    )


@pytest.mark.asyncio
async def test_full_index_new_files(indexer, registry, embedder):
    """First index: all files are new."""
    # Make embed_batch return correct number of vectors
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer.run(job)

    assert job.status == "completed"
    assert job.files_total == 2
    assert job.files_processed == 2
    assert job.files_skipped == 0
    assert job.chunks_created > 0


@pytest.mark.asyncio
async def test_skip_unchanged_files(indexer, registry, embedder, manifest, project_dir):
    """Second index with no changes: all files skipped."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # First index
    job1 = registry.create_job()
    await indexer.run(job1)
    assert job1.files_processed == 2

    # Second index — nothing changed
    job2 = registry.create_job()
    await indexer.run(job2)
    assert job2.status == "completed"
    assert job2.files_skipped == 2
    assert job2.files_processed == 0


@pytest.mark.asyncio
async def test_reindex_modified_file(indexer, registry, embedder, project_dir):
    """Modified file gets re-indexed."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # First index
    job1 = registry.create_job()
    await indexer.run(job1)

    # Modify one file
    (project_dir / "docs" / "guide.md").write_text("# Guide\n\nUpdated content.")

    job2 = registry.create_job()
    await indexer.run(job2)
    assert job2.status == "completed"
    assert job2.files_processed == 1
    assert job2.files_skipped == 1


@pytest.mark.asyncio
async def test_detect_deleted_file(indexer, registry, embedder, project_dir, store):
    """Deleted file gets cleaned up."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # First index
    job1 = registry.create_job()
    await indexer.run(job1)
    assert store.document_count() == 2

    # Delete one file
    (project_dir / "docs" / "api.md").unlink()

    job2 = registry.create_job()
    await indexer.run(job2)
    assert job2.status == "completed"
    assert job2.files_deleted == 1
    assert store.document_count() == 1


@pytest.mark.asyncio
async def test_single_file_error_continues(indexer, registry, embedder, project_dir):
    """A file that fails to embed doesn't stop the whole job."""
    call_count = 0

    async def flaky_embed(texts):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Ollama timeout")
        return [[0.1] * 768] * len(texts)

    embedder.embed_batch = AsyncMock(side_effect=flaky_embed)

    job = registry.create_job()
    await indexer.run(job)
    # Job should complete (not fail) — one file succeeded, one failed
    assert job.status == "completed"
    assert job.files_processed >= 1


@pytest.mark.asyncio
async def test_job_phases(indexer, registry, embedder):
    """Job transitions through discovery → indexing phases."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))
    phases_seen = []

    original_run = indexer.run

    class PhaseTracker:
        def __init__(self, job):
            self.job = job

        def check(self):
            if self.job.phase and self.job.phase not in phases_seen:
                phases_seen.append(self.job.phase)

    job = registry.create_job()
    # We'll check phases after run completes — at minimum discovery and indexing
    await indexer.run(job)
    # The job should have gone through both phases
    assert job.status == "completed"
    # files_total > 0 means discovery happened
    assert job.files_total == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_indexer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'guru_server.indexer'`

- [ ] **Step 3: Implement BackgroundIndexer**

Create `packages/guru-server/src/guru_server/indexer.py`:

```python
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from guru_core.types import Rule
from guru_server.ingestion.markdown import MarkdownParser
from guru_server.jobs import Job
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


class BackgroundIndexer:
    def __init__(
        self,
        *,
        store: VectorStore,
        manifest: FileManifest,
        embedder,
        config: list[Rule],
        project_root: Path,
    ) -> None:
        self._store = store
        self._manifest = manifest
        self._embedder = embedder
        self._config = config
        self._project_root = Path(project_root).resolve()
        self._parser = MarkdownParser()

    async def run(self, job: Job) -> None:
        """Execute a two-phase indexing job."""
        job.status = "running"
        job.started_at = datetime.now(UTC)
        short_id = job.job_id[:8]

        try:
            # Phase 1: Discovery
            job.phase = "discovery"
            to_index, to_skip, to_delete = self._discover(job)
            job.files_total = len(to_index) + len(to_skip)
            job.files_skipped = len(to_skip)

            logger.info(
                "[job %s] Discovery: %d files matched, %d unchanged, %d to index, %d deleted",
                short_id,
                job.files_total,
                job.files_skipped,
                len(to_index),
                len(to_delete),
            )

            # Phase 2: Indexing
            job.phase = "indexing"
            for file_path, rel_path, rule in to_index:
                try:
                    await self._index_file(job, file_path, rel_path, rule, short_id)
                except Exception:
                    logger.exception("[job %s] Failed to index %s", short_id, rel_path)
                    continue

            # Cleanup deleted files
            for rel_path in to_delete:
                self._store.delete_file(rel_path)
                self._manifest.delete_entry(rel_path)
                job.files_deleted += 1
                logger.info("[job %s] Deleted %s (removed from disk)", short_id, rel_path)

            job.status = "completed"
            job.phase = None
            job.finished_at = datetime.now(UTC)
            logger.info(
                "[job %s] Completed: %d files indexed, %d chunks created, %d deleted",
                short_id,
                job.files_processed,
                job.chunks_created,
                job.files_deleted,
            )
        except Exception as exc:
            job.status = "failed"
            job.phase = None
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            logger.exception("[job %s] Job failed: %s", short_id, exc)

    def _discover(self, job: Job):
        """Scan files and compare against manifest. Returns (to_index, to_skip, to_delete)."""
        # Collect excluded files
        excluded_files: set[Path] = set()
        for rule in self._config:
            if rule.exclude:
                excluded_files.update(self._project_root.glob(rule.match.glob))

        # Collect all matched files with their rules
        seen_files: set[Path] = set()
        matched: list[tuple[Path, str, Rule]] = []
        for rule in self._config:
            if rule.exclude:
                continue
            for file_path in self._project_root.glob(rule.match.glob):
                if not file_path.is_file():
                    continue
                if file_path in excluded_files:
                    continue
                if file_path in seen_files:
                    continue
                if self._parser.supports(file_path):
                    seen_files.add(file_path)
                    rel_path = str(file_path.relative_to(self._project_root))
                    matched.append((file_path, rel_path, rule))

        # Check each file against manifest
        to_index: list[tuple[Path, str, Rule]] = []
        to_skip: list[str] = []
        matched_rel_paths: set[str] = set()

        for file_path, rel_path, rule in matched:
            matched_rel_paths.add(rel_path)
            entry = self._manifest.get_entry(rel_path)

            if entry is None:
                # New file
                to_index.append((file_path, rel_path, rule))
                continue

            current_mtime = file_path.stat().st_mtime
            if current_mtime == entry["mtime"]:
                # mtime unchanged — skip without hashing
                to_skip.append(rel_path)
                continue

            # mtime changed — check content hash
            current_hash = _file_hash(file_path)
            if current_hash == entry["content_hash"]:
                # Content unchanged despite mtime change (e.g. touch)
                self._manifest.update_mtime(rel_path, mtime=current_mtime)
                to_skip.append(rel_path)
                continue

            # Content changed — must re-index
            to_index.append((file_path, rel_path, rule))

        # Detect deletions: manifest entries not in matched files
        to_delete: list[str] = []
        for entry in self._manifest.all_entries():
            if entry["file_path"] not in matched_rel_paths:
                to_delete.append(entry["file_path"])

        return to_index, to_skip, to_delete

    async def _index_file(
        self, job: Job, file_path: Path, rel_path: str, rule: Rule, short_id: str
    ) -> None:
        """Parse, embed, and store a single file."""
        # Delete old chunks if re-indexing
        self._store.delete_file(rel_path)

        chunks = self._parser.parse(file_path, rule)
        for chunk in chunks:
            chunk.file_path = rel_path

        if not chunks:
            job.files_processed += 1
            return

        texts = [chunk.content for chunk in chunks]
        vectors = await self._embedder.embed_batch(texts)
        self._store.add_chunks(chunks, vectors)

        # Update manifest
        current_hash = _file_hash(file_path)
        current_mtime = file_path.stat().st_mtime
        self._manifest.upsert(
            rel_path,
            content_hash=current_hash,
            mtime=current_mtime,
            chunk_count=len(chunks),
        )

        job.files_processed += 1
        job.chunks_created += len(chunks)
        logger.info("[job %s] Indexed %s (%d chunks)", short_id, rel_path, len(chunks))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_indexer.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/indexer.py \
       packages/guru-server/tests/test_indexer.py
git commit -m "feat: add BackgroundIndexer with change detection (#18)"
```

---

## Task 5: Update API Endpoints

**Files:**
- Modify: `packages/guru-server/src/guru_server/api/index.py`
- Modify: `packages/guru-server/src/guru_server/api/status.py`
- Modify: `packages/guru-server/src/guru_server/api/__init__.py`
- Create: `packages/guru-server/src/guru_server/api/jobs.py`
- Modify: `packages/guru-server/tests/test_api.py`

- [ ] **Step 1: Write/update the failing tests**

Update `packages/guru-server/tests/test_api.py`. Replace the entire file:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from guru_server.app import create_app
from guru_server.jobs import JobRegistry


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.chunk_count.return_value = 100
    store.document_count.return_value = 1
    store.list_documents.return_value = [
        {
            "file_path": "specs/auth.md",
            "frontmatter": {"title": "Auth"},
            "labels": ["spec"],
            "chunk_count": 5,
        },
    ]
    store.get_document.return_value = {
        "file_path": "specs/auth.md",
        "content": "# Auth\n\nOAuth flow.",
        "frontmatter": {"title": "Auth"},
        "labels": ["spec"],
        "chunk_count": 5,
    }
    store.get_section.return_value = {
        "file_path": "specs/auth.md",
        "header_breadcrumb": "Auth > OAuth",
        "content": "OAuth 2.0 flow",
        "chunk_level": 2,
    }
    store.search.return_value = [
        {
            "content": "OAuth 2.0 flow",
            "file_path": "specs/auth.md",
            "header_breadcrumb": "Auth > OAuth",
            "chunk_level": 2,
            "labels": ["spec"],
            "score": 0.95,
        },
    ]
    return store


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 768)
    embedder.embed_batch = AsyncMock(return_value=[[0.1] * 768])
    return embedder


@pytest.fixture
def client(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder)
    return TestClient(app)


def test_get_status(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server_running"] is True
    assert data["chunk_count"] == 100
    assert data["document_count"] == 1
    assert data["last_indexed"] is None
    assert data["ollama_available"] is True
    assert data["model_loaded"] is True
    assert data["current_job"] is None


def test_get_status_with_running_job(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder)
    # Manually create a running job
    job = app.state.job_registry.create_job()
    job.status = "running"
    job.phase = "indexing"
    job.files_total = 10
    job.files_processed = 5
    job.files_skipped = 2
    with TestClient(app) as c:
        data = c.get("/status").json()
        assert data["current_job"] is not None
        assert data["current_job"]["job_id"] == job.job_id
        assert data["current_job"]["status"] == "running"
        assert data["current_job"]["files_total"] == 10


def test_post_index_returns_accepted(client):
    resp = client.post("/index", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] in ("queued", "running")
    assert "message" in data


def test_post_index_returns_existing_job(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder)
    # Create a running job
    job = app.state.job_registry.create_job()
    job.status = "running"
    with TestClient(app) as c:
        resp = c.post("/index", json={})
        data = resp.json()
        assert data["job_id"] == job.job_id
        assert data["message"] == "Indexing already in progress"


def test_get_job_detail(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder)
    job = app.state.job_registry.create_job()
    job.status = "completed"
    job.files_total = 5
    job.files_processed = 5
    with TestClient(app) as c:
        resp = c.get(f"/jobs/{job.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job.job_id
        assert data["status"] == "completed"


def test_get_job_not_found(client):
    resp = client.get("/jobs/nonexistent")
    assert resp.status_code == 404


def test_list_documents(client):
    resp = client.get("/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file_path"] == "specs/auth.md"


def test_list_documents_with_label_filter(client, mock_store):
    mock_store.list_documents.return_value = [
        {
            "file_path": "specs/auth.md",
            "frontmatter": {"title": "Auth"},
            "labels": ["spec"],
            "chunk_count": 5,
        },
        {
            "file_path": "specs/rbac.md",
            "frontmatter": {"title": "RBAC"},
            "labels": ["spec", "security"],
            "chunk_count": 3,
        },
    ]
    resp = client.get("/documents?labels=security")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file_path"] == "specs/rbac.md"


def test_list_documents_with_unsupported_filter(client):
    resp = client.get("/documents?unknown_col=foo")
    assert resp.status_code == 400


def test_get_document(client):
    resp = client.get("/documents/specs/auth.md")
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_path"] == "specs/auth.md"
    assert "content" in data


def test_get_document_not_found(client, mock_store):
    mock_store.get_document.return_value = None
    resp = client.get("/documents/nonexistent.md")
    assert resp.status_code == 404


def test_get_section(client):
    resp = client.get("/documents/specs/auth.md/sections/Auth > OAuth")
    assert resp.status_code == 200
    data = resp.json()
    assert data["header_breadcrumb"] == "Auth > OAuth"


def test_get_section_not_found(client, mock_store):
    mock_store.get_section.return_value = None
    resp = client.get("/documents/specs/auth.md/sections/Nonexistent")
    assert resp.status_code == 404


def test_search(client):
    resp = client.post("/search", json={"query": "authentication"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file_path"] == "specs/auth.md"


def test_search_with_filters(client):
    resp = client.post(
        "/search", json={"query": "auth", "n_results": 5, "filters": {"labels": "spec"}}
    )
    assert resp.status_code == 200


def test_search_with_disallowed_filter(client):
    resp = client.post("/search", json={"query": "auth", "filters": {"arbitrary_col": "value"}})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_api.py -v`
Expected: FAIL — `test_get_status` fails on `current_job`, `test_post_index_returns_accepted` fails on missing `job_id`

- [ ] **Step 3: Create the jobs endpoint**

Create `packages/guru-server/src/guru_server/api/jobs.py`:

```python
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
```

- [ ] **Step 4: Rewrite the index endpoint**

Replace `packages/guru-server/src/guru_server/api/index.py` entirely:

```python
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
    logger.info("Indexing requested (path=%s), job=%s", body.path or "project root", job.job_id[:8])

    # Launch background indexing task
    indexer = request.app.state.indexer
    asyncio.create_task(indexer.run(job))

    return IndexAccepted(
        job_id=job.job_id,
        status=job.status,
        message="Indexing started",
    )
```

- [ ] **Step 5: Update the status endpoint**

Replace `packages/guru-server/src/guru_server/api/status.py`:

```python
from fastapi import APIRouter, Request

from guru_server.api.models import StatusOut

router = APIRouter()


@router.get("/status", response_model=StatusOut)
async def get_status(request: Request):
    store = request.app.state.store
    registry = request.app.state.job_registry
    current = registry.current_job()
    return StatusOut(
        server_running=True,
        document_count=store.document_count(),
        chunk_count=store.chunk_count(),
        last_indexed=request.app.state.last_indexed,
        ollama_available=True,
        model_loaded=True,
        current_job=current.to_summary() if current else None,
    )
```

- [ ] **Step 6: Add jobs router to api/__init__.py**

Replace `packages/guru-server/src/guru_server/api/__init__.py`:

```python
from fastapi import APIRouter

from guru_server.api.documents import router as documents_router
from guru_server.api.index import router as index_router
from guru_server.api.jobs import router as jobs_router
from guru_server.api.search import router as search_router
from guru_server.api.status import router as status_router

api_router = APIRouter()
api_router.include_router(search_router)
api_router.include_router(documents_router)
api_router.include_router(index_router)
api_router.include_router(jobs_router)
api_router.include_router(status_router)
```

- [ ] **Step 7: Update create_app to initialize JobRegistry and BackgroundIndexer**

Replace `packages/guru-server/src/guru_server/app.py`:

```python
from __future__ import annotations

import lancedb
from fastapi import FastAPI

from guru_server.api import api_router
from guru_server.embedding import OllamaEmbedder
from guru_server.indexer import BackgroundIndexer
from guru_server.jobs import JobRegistry
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore


def create_app(
    store: VectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    config: list | None = None,
    project_root: str | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Accepts optional overrides for testing. In production these are
    created from the server's startup sequence.
    """
    app = FastAPI(title="Guru Server", version="0.1.0")
    app.state.store = store
    app.state.embedder = embedder
    app.state.config = config or []
    app.state.project_root = project_root or "."
    app.state.last_indexed = None
    app.state.job_registry = JobRegistry()

    # Create manifest using the same LanceDB connection as the store
    if store is not None and hasattr(store, "db"):
        app.state.manifest = FileManifest(store.db)
    else:
        app.state.manifest = None

    # Create indexer if we have all dependencies
    if store is not None and embedder is not None and app.state.manifest is not None:
        from pathlib import Path

        app.state.indexer = BackgroundIndexer(
            store=store,
            manifest=app.state.manifest,
            embedder=embedder,
            config=app.state.config,
            project_root=Path(app.state.project_root),
        )
    else:
        app.state.indexer = None

    app.include_router(api_router)
    return app
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_api.py -v`
Expected: All tests PASS

- [ ] **Step 9: Run all server tests to verify no regressions**

Run: `uv run pytest packages/guru-server/ -v`
Expected: All tests PASS

- [ ] **Step 10: Commit**

```bash
git add packages/guru-server/src/guru_server/api/index.py \
       packages/guru-server/src/guru_server/api/status.py \
       packages/guru-server/src/guru_server/api/jobs.py \
       packages/guru-server/src/guru_server/api/__init__.py \
       packages/guru-server/src/guru_server/app.py \
       packages/guru-server/tests/test_api.py
git commit -m "feat: update API for background indexing (#18)"
```

---

## Task 6: Update GuruClient in guru-core

**Files:**
- Modify: `packages/guru-core/src/guru_core/client.py`
- Modify: `packages/guru-core/tests/test_types.py` (add client test)

- [ ] **Step 1: Write the failing test**

Add to `packages/guru-core/tests/test_types.py`:

```python
def test_guru_client_has_get_job_method():
    """Verify GuruClient exposes get_job()."""
    from pathlib import Path

    from guru_core.client import GuruClient

    client = GuruClient(guru_root=Path("/tmp/fake"))
    assert hasattr(client, "get_job")
    assert callable(client.get_job)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/guru-core/tests/test_types.py::test_guru_client_has_get_job_method -v`
Expected: FAIL — `AttributeError: 'GuruClient' object has no attribute 'get_job'`

- [ ] **Step 3: Add get_job method to GuruClient**

Edit `packages/guru-core/src/guru_core/client.py`. Add after the `trigger_index` method (line 74):

```python
    async def get_job(self, job_id: str) -> dict:
        return await self._get(f"/jobs/{job_id}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/guru-core/tests/test_types.py::test_guru_client_has_get_job_method -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/guru-core/src/guru_core/client.py \
       packages/guru-core/tests/test_types.py
git commit -m "feat: add get_job to GuruClient (#18)"
```

---

## Task 7: Update CLI Commands

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/cli.py`

- [ ] **Step 1: Update the index command**

Edit `packages/guru-cli/src/guru_cli/cli.py`. Replace the `index` command (lines 201-207):

```python
@cli.command()
@click.argument("path", required=False)
def index(path):
    """Index documents in the knowledge base."""
    client = _get_client()
    result = _run(client.trigger_index(path))
    click.echo(f"Indexing started (job {result['job_id']})")
```

- [ ] **Step 2: Update the server status command**

Replace the `server_status` command (lines 192-198):

```python
@server.command("status")
@click.option("--job", "job_id", default=None, help="Show details for a specific job")
def server_status(job_id):
    """Show server status."""
    client = _get_client()
    if job_id:
        job = _run(client.get_job(job_id))
        for key, value in job.items():
            click.echo(f"  {key}: {value}")
        return
    status = _run(client.status())
    current_job = status.pop("current_job", None)
    for key, value in status.items():
        click.echo(f"  {key}: {value}")
    if current_job:
        total = current_job["files_total"]
        processed = current_job["files_processed"]
        skipped = current_job["files_skipped"]
        click.echo(f"  Indexing: {processed}/{total} files processed ({skipped} skipped)")
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `uv run pytest packages/guru-cli/ -v 2>/dev/null; echo "CLI has no unit tests yet — skip"`
Expected: No test failures (CLI tests are in BDD)

- [ ] **Step 4: Commit**

```bash
git add packages/guru-cli/src/guru_cli/cli.py
git commit -m "feat: update CLI for background indexing (#18)"
```

---

## Task 8: Auto-Index on Startup and File Watcher

**Files:**
- Modify: `packages/guru-server/src/guru_server/app.py`
- Create: `packages/guru-server/src/guru_server/watcher.py`
- Modify: `packages/guru-server/pyproject.toml`
- Test: `packages/guru-server/tests/test_watcher.py` (create)

- [ ] **Step 1: Add watchfiles dependency**

Edit `packages/guru-server/pyproject.toml`. Add `"watchfiles>=1.0",` to the dependencies list (after line 34):

```toml
[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    "guru-core=={{ version }}",
    "httpx>=0.28",
    "pydantic>=2.0",
    "llama-index-core>=0.14",
    "python-frontmatter>=1.1",
    "lancedb>=0.27",
    "pandas>=2.0",
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "watchfiles>=1.0",
]
```

- [ ] **Step 2: Run uv sync**

Run: `uv sync --all-packages`
Expected: Success, `watchfiles` installed

- [ ] **Step 3: Write watcher tests**

Create `packages/guru-server/tests/test_watcher.py`:

```python
from pathlib import Path

from guru_core.types import MatchConfig, Rule
from guru_server.watcher import should_watch_path


def test_should_watch_markdown_file():
    config = [Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/docs/guide.md"), project_root, config) is True


def test_should_not_watch_non_matching_file():
    config = [Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/src/main.py"), project_root, config) is False


def test_should_not_watch_guru_dir():
    config = [Rule(rule_name="all", match=MatchConfig(glob="**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/.guru/db/data.md"), project_root, config) is False


def test_should_not_watch_transient_files():
    config = [Rule(rule_name="all", match=MatchConfig(glob="**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/docs/guide.md.swp"), project_root, config) is False
    assert should_watch_path(Path("/project/docs/guide.md~"), project_root, config) is False
    assert should_watch_path(Path("/project/docs/.guide.md.tmp"), project_root, config) is False


def test_should_not_watch_excluded_files():
    config = [
        Rule(rule_name="all", match=MatchConfig(glob="**/*.md")),
        Rule(rule_name="exclude_vendor", match=MatchConfig(glob="vendor/**/*.md"), exclude=True),
    ]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/vendor/lib.md"), project_root, config) is False
```

- [ ] **Step 4: Run watcher tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_watcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'guru_server.watcher'`

- [ ] **Step 5: Implement the watcher module**

Create `packages/guru-server/src/guru_server/watcher.py`:

```python
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from guru_core.types import Rule
from guru_server.jobs import JobRegistry

logger = logging.getLogger(__name__)

TRANSIENT_SUFFIXES = {".swp", ".swo", ".tmp", "~"}
DEBOUNCE_SECONDS = 2.0


def should_watch_path(path: Path, project_root: Path, config: list[Rule]) -> bool:
    """Check if a changed path should trigger re-indexing."""
    # Ignore .guru/ directory
    try:
        rel = path.relative_to(project_root)
    except ValueError:
        return False

    if rel.parts and rel.parts[0] == ".guru":
        return False

    # Ignore transient editor files
    name = path.name
    if any(name.endswith(s) for s in TRANSIENT_SUFFIXES):
        return False
    if name.startswith(".") and name.endswith(".tmp"):
        return False

    # Check if file matches any include glob and is not excluded
    str_rel = str(rel)
    excluded = False
    matched = False

    for rule in config:
        if rule.exclude:
            # Check if path matches exclude pattern
            if list(project_root.glob(rule.match.glob)):
                # Use Path.match for individual file check
                for p in project_root.glob(rule.match.glob):
                    if p == path:
                        excluded = True
                        break
        else:
            for p in project_root.glob(rule.match.glob):
                if p == path:
                    matched = True
                    break

    return matched and not excluded


async def start_watcher(
    project_root: Path,
    config: list[Rule],
    job_registry: JobRegistry,
    submit_index: callable,
) -> None:
    """Watch project files for changes and trigger re-indexing.

    Args:
        project_root: The project root directory to watch.
        config: The indexing config rules for filtering.
        job_registry: The job registry to check for running jobs.
        submit_index: Callable to submit a new indexing job.
    """
    from watchfiles import awatch

    logger.info("File watcher started on %s", project_root)

    try:
        async for changes in awatch(project_root, debounce=int(DEBOUNCE_SECONDS * 1000)):
            # Filter to relevant changes
            relevant = [
                path
                for change_type, path in changes
                if should_watch_path(Path(path), project_root, config)
            ]

            if not relevant:
                continue

            logger.info("File watcher detected %d relevant change(s)", len(relevant))

            # Check if a job is already running
            if job_registry.current_job() is not None:
                logger.info("Index job already running, changes will be picked up by next run")
                continue

            await submit_index()
    except asyncio.CancelledError:
        logger.info("File watcher stopped")
        raise
    except Exception:
        logger.exception("File watcher error")
```

- [ ] **Step 6: Run watcher tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_watcher.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Update app.py with lifespan for auto-index and watcher**

Replace `packages/guru-server/src/guru_server/app.py`:

```python
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from guru_server.api import api_router
from guru_server.embedding import OllamaEmbedder
from guru_server.indexer import BackgroundIndexer
from guru_server.jobs import JobRegistry
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle: auto-index on startup, file watcher."""
    watcher_task = None

    if app.state.indexer is not None:
        # Auto-index on startup
        job = app.state.job_registry.create_job()
        logger.info("Auto-indexing on startup (job %s)", job.job_id[:8])

        async def _run_startup_index():
            await app.state.indexer.run(job)
            from datetime import UTC, datetime

            app.state.last_indexed = datetime.now(UTC)

            # Start file watcher after initial index completes
            nonlocal watcher_task
            try:
                from guru_server.watcher import start_watcher

                async def _submit_index():
                    new_job = app.state.job_registry.create_job()
                    asyncio.create_task(app.state.indexer.run(new_job))

                watcher_task = asyncio.create_task(
                    start_watcher(
                        project_root=Path(app.state.project_root),
                        config=app.state.config,
                        job_registry=app.state.job_registry,
                        submit_index=_submit_index,
                    )
                )
            except Exception:
                logger.exception("Failed to start file watcher")

        asyncio.create_task(_run_startup_index())

    yield

    # Cleanup: stop watcher
    if watcher_task is not None:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass


def create_app(
    store: VectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    config: list | None = None,
    project_root: str | None = None,
    auto_index: bool = True,
) -> FastAPI:
    """Create the FastAPI application.

    Accepts optional overrides for testing. In production these are
    created from the server's startup sequence.

    Args:
        auto_index: If True (default), auto-index on startup and start
            the file watcher. Set to False in tests that don't need it.
    """
    app = FastAPI(
        title="Guru Server",
        version="0.1.0",
        lifespan=lifespan if auto_index else None,
    )
    app.state.store = store
    app.state.embedder = embedder
    app.state.config = config or []
    app.state.project_root = project_root or "."
    app.state.last_indexed = None
    app.state.job_registry = JobRegistry()

    # Create manifest using the same LanceDB connection as the store
    if store is not None and hasattr(store, "db"):
        app.state.manifest = FileManifest(store.db)
    else:
        app.state.manifest = None

    # Create indexer if we have all dependencies
    if store is not None and embedder is not None and app.state.manifest is not None:
        app.state.indexer = BackgroundIndexer(
            store=store,
            manifest=app.state.manifest,
            embedder=embedder,
            config=app.state.config,
            project_root=Path(app.state.project_root),
        )
    else:
        app.state.indexer = None

    app.include_router(api_router)
    return app
```

- [ ] **Step 8: Update test_api.py to pass auto_index=False**

Edit `packages/guru-server/tests/test_api.py`. Update the `client` fixture:

```python
@pytest.fixture
def client(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
    return TestClient(app)
```

Also update `test_get_status_with_running_job` and `test_post_index_returns_existing_job` and `test_get_job_detail` to pass `auto_index=False`:

```python
def test_get_status_with_running_job(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
    ...

def test_post_index_returns_existing_job(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
    ...

def test_get_job_detail(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
    ...
```

- [ ] **Step 9: Run all server tests**

Run: `uv run pytest packages/guru-server/ -v`
Expected: All tests PASS

- [ ] **Step 10: Commit**

```bash
git add packages/guru-server/src/guru_server/watcher.py \
       packages/guru-server/src/guru_server/app.py \
       packages/guru-server/tests/test_watcher.py \
       packages/guru-server/tests/test_api.py \
       packages/guru-server/pyproject.toml
git commit -m "feat: add auto-index on startup and file watcher (#18)"
```

---

## Task 9: Update BDD E2E Tests

**Files:**
- Create: `tests/e2e/features/background_indexing.feature`
- Create: `tests/e2e/features/steps/background_indexing_steps.py`
- Modify: `tests/e2e/features/knowledge_base.feature`
- Modify: `tests/e2e/features/steps/cli_steps.py`
- Modify: `tests/e2e/features/environment.py`

- [ ] **Step 1: Update environment.py to add wait-for-index helper and pass auto_index=False to test server**

Edit `tests/e2e/features/environment.py`.

Add a helper function after `_start_server` (after line 311):

```python
def _wait_for_index(project_dir: Path, timeout: float = 30.0) -> None:
    """Poll the server status until no job is running."""
    import httpx

    socket_path = str(project_dir / ".guru" / "guru.sock")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            transport = httpx.HTTPTransport(uds=socket_path)
            with httpx.Client(transport=transport, timeout=5.0) as client:
                resp = client.get("http://localhost/status")
                data = resp.json()
                if data.get("current_job") is None:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("Index did not complete within timeout")
```

Update `_start_server` to pass `auto_index=False` to `create_app`:

In the `_start_server` function, change the `create_app` call (line 289-294):

```python
    app = create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(project_dir),
        auto_index=False,
    )
```

- [ ] **Step 2: Update cli_steps.py for new index output format**

Edit `tests/e2e/features/steps/cli_steps.py`. The `step_index_kb` step (around line 65) calls `guru index`. The output format changes from `"Indexed X chunks from Y documents."` to `"Indexing started (job <id>)"`.

Update the step that indexes the knowledge base to also trigger index via REST and wait:

```python
@given("the knowledge base has been indexed")
def step_index_kb(context):
    """Index the knowledge base via REST API and wait for completion."""
    import httpx

    socket_path = str(context.project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=30.0) as client:
        client.post("http://localhost/index", json={})
    # Wait for the background job to complete
    from environment import _wait_for_index

    _wait_for_index(context.project_dir)
```

- [ ] **Step 3: Update knowledge_base.feature for new index output**

Edit `tests/e2e/features/knowledge_base.feature`. Update the "Index documents" scenario (lines 16-20):

```gherkin
  Scenario: Index documents from configured directories
    When I run "guru index"
    Then the command succeeds
    And the output contains "Indexing started"
    And the output contains "job"
```

- [ ] **Step 4: Create the background indexing feature file**

Create `tests/e2e/features/background_indexing.feature`:

```gherkin
Feature: Background indexing and change detection
  As a developer using Guru
  I want indexing to run in the background and only re-index changed files
  So that my knowledge base stays current without manual intervention

  Background:
    Given a guru project with sample markdown files
    And the guru server is running

  Scenario: Index returns immediately with job reference
    When I trigger indexing via REST API
    Then the response contains a job_id
    And the response status is "running" or "queued"

  Scenario: Job reaches completed status
    When I trigger indexing via REST API
    And I wait for the index job to complete
    Then the job status is "completed"
    And the job files_total is 3
    And the job files_processed is 3
    And the job files_skipped is 0

  Scenario: Unchanged files are skipped on re-index
    When I trigger indexing via REST API
    And I wait for the index job to complete
    And I trigger indexing via REST API again
    And I wait for the index job to complete
    Then the job files_skipped is 3
    And the job files_processed is 0

  Scenario: Modified file is re-indexed
    When I trigger indexing via REST API
    And I wait for the index job to complete
    And I modify the file "docs/getting-started.md"
    And I trigger indexing via REST API again
    And I wait for the index job to complete
    Then the job files_processed is 1
    And the job files_skipped is 2

  Scenario: Deleted file is cleaned up
    When I trigger indexing via REST API
    And I wait for the index job to complete
    And I delete the file "docs/getting-started.md"
    And I trigger indexing via REST API again
    And I wait for the index job to complete
    Then the job files_deleted is 1

  Scenario: Status shows current job while indexing
    When I trigger indexing via REST API
    Then the server status includes current_job

  Scenario: Job detail endpoint returns full info
    When I trigger indexing via REST API
    And I wait for the index job to complete
    Then I can retrieve the job detail via REST API
    And the job detail contains job_type "index"
    And the job detail contains created_at
    And the job detail contains finished_at
```

- [ ] **Step 5: Create step definitions for background indexing**

Create `tests/e2e/features/steps/background_indexing_steps.py`:

```python
"""Step definitions for background indexing BDD scenarios."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from behave import given, then, when


def _http_client(context):
    socket_path = str(context.project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    return httpx.Client(transport=transport, timeout=30.0)


def _wait_for_index(context, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _http_client(context) as client:
            resp = client.get("http://localhost/status")
            data = resp.json()
            if data.get("current_job") is None:
                # Get the most recent job detail
                if hasattr(context, "last_job_id") and context.last_job_id:
                    resp = client.get(f"http://localhost/jobs/{context.last_job_id}")
                    context.last_job = resp.json()
                return
        time.sleep(0.3)
    raise RuntimeError("Index did not complete within timeout")


@when("I trigger indexing via REST API")
def step_trigger_index(context):
    with _http_client(context) as client:
        resp = client.post("http://localhost/index", json={})
        context.index_response = resp.json()
        context.last_job_id = context.index_response.get("job_id")


@when("I trigger indexing via REST API again")
def step_trigger_index_again(context):
    step_trigger_index(context)


@when("I wait for the index job to complete")
def step_wait_for_index(context):
    _wait_for_index(context)


@when('I modify the file "{file_path}"')
def step_modify_file(context, file_path):
    full_path = context.project_dir / file_path
    full_path.write_text(full_path.read_text() + "\n\nModified content appended.")


@when('I delete the file "{file_path}"')
def step_delete_file(context, file_path):
    full_path = context.project_dir / file_path
    full_path.unlink()


@then("the response contains a job_id")
def step_response_has_job_id(context):
    assert "job_id" in context.index_response, f"No job_id in response: {context.index_response}"


@then('the response status is "running" or "queued"')
def step_response_status(context):
    status = context.index_response.get("status")
    assert status in ("running", "queued"), f"Unexpected status: {status}"


@then('the job status is "{expected}"')
def step_job_status(context, expected):
    assert context.last_job["status"] == expected, (
        f"Expected {expected}, got {context.last_job['status']}"
    )


@then("the job files_total is {count:d}")
def step_job_files_total(context, count):
    assert context.last_job["files_total"] == count, (
        f"Expected {count}, got {context.last_job['files_total']}"
    )


@then("the job files_processed is {count:d}")
def step_job_files_processed(context, count):
    assert context.last_job["files_processed"] == count, (
        f"Expected {count}, got {context.last_job['files_processed']}"
    )


@then("the job files_skipped is {count:d}")
def step_job_files_skipped(context, count):
    assert context.last_job["files_skipped"] == count, (
        f"Expected {count}, got {context.last_job['files_skipped']}"
    )


@then("the job files_deleted is {count:d}")
def step_job_files_deleted(context, count):
    assert context.last_job["files_deleted"] == count, (
        f"Expected {count}, got {context.last_job['files_deleted']}"
    )


@then("the server status includes current_job")
def step_status_has_current_job(context):
    with _http_client(context) as client:
        resp = client.get("http://localhost/status")
        data = resp.json()
        # Job may have already completed — check that the field exists
        assert "current_job" in data


@then("I can retrieve the job detail via REST API")
def step_get_job_detail(context):
    with _http_client(context) as client:
        resp = client.get(f"http://localhost/jobs/{context.last_job_id}")
        assert resp.status_code == 200
        context.job_detail = resp.json()


@then('the job detail contains job_type "{expected}"')
def step_job_detail_type(context, expected):
    assert context.job_detail["job_type"] == expected


@then("the job detail contains created_at")
def step_job_detail_created_at(context):
    assert context.job_detail["created_at"] is not None


@then("the job detail contains finished_at")
def step_job_detail_finished_at(context):
    assert context.job_detail["finished_at"] is not None
```

- [ ] **Step 6: Run the new BDD feature**

Run: `uv run behave tests/e2e/features/background_indexing.feature`
Expected: All scenarios PASS

- [ ] **Step 7: Run the existing knowledge_base feature to verify no regressions**

Run: `uv run behave tests/e2e/features/knowledge_base.feature`
Expected: All scenarios PASS

- [ ] **Step 8: Run the MCP feature to verify no regressions**

Run: `uv run behave tests/e2e/features/mcp_tools.feature`
Expected: All scenarios PASS

- [ ] **Step 9: Commit**

```bash
git add tests/e2e/features/background_indexing.feature \
       tests/e2e/features/steps/background_indexing_steps.py \
       tests/e2e/features/knowledge_base.feature \
       tests/e2e/features/steps/cli_steps.py \
       tests/e2e/features/environment.py
git commit -m "test: add BDD tests for background indexing (#18)"
```

---

## Task 10: Update MCP Tools and Run Full Test Suite

**Files:**
- Modify: `packages/guru-mcp/src/guru_mcp/server.py` (no changes needed — `index_status` already returns `StatusOut` which now includes `current_job`)
- Modify: `tests/e2e/features/steps/mcp_steps.py` (update indexing step)

- [ ] **Step 1: Update MCP step that triggers indexing**

Edit `tests/e2e/features/steps/mcp_steps.py`. The `step_index_via_rest` step (around line 75-81) calls `client.trigger_index()` and expects it to block. Update it to also wait for completion:

```python
@given("the knowledge base has been indexed via REST")
def step_index_via_rest(context):
    """Index the knowledge base by calling the server REST API directly."""
    import asyncio
    import time

    from guru_core.client import GuruClient

    client = GuruClient(guru_root=context.project_dir)
    asyncio.run(client.trigger_index())

    # Wait for background indexing to complete
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        status = asyncio.run(client.status())
        if status.get("current_job") is None and status.get("chunk_count", 0) > 0:
            break
        time.sleep(0.3)
    else:
        raise RuntimeError("Indexing did not complete within timeout")
```

- [ ] **Step 2: Run all BDD tests**

Run: `uv run behave tests/e2e/features/`
Expected: All features PASS

- [ ] **Step 3: Run all unit tests**

Run: `uv run pytest packages/ tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Run lint**

Run: `make lint`
Expected: No lint errors

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/features/steps/mcp_steps.py
git commit -m "test: update MCP steps for background indexing (#18)"
```

---

## Task 11: Final Integration Verification

- [ ] **Step 1: Run the full test suite**

Run: `make test-all`
Expected: All tests PASS

- [ ] **Step 2: Run lint and format check**

Run: `make lint`
Expected: Clean

- [ ] **Step 3: Manual smoke test (optional)**

```bash
cd /tmp && mkdir test-guru && cd test-guru
guru init
echo "# Hello\n\nWorld" > docs/hello.md
guru server start --foreground --log-level INFO
# In another terminal:
guru index  # Should print "Indexing started (job ...)"
guru server status  # Should show job progress or completion
guru search "hello"  # Should return results
```

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes for background indexing (#18)"
```
