# Background Indexing and Change Detection

**Issue:** #18 — Automatic indexing on background and re-indexing of changed documents  
**Date:** 2026-04-10  
**Status:** Approved

---

## Problem

Indexing is manual-only (`guru index`), synchronous (blocks until complete), and
always re-indexes every file regardless of whether it changed. There is no visibility
into indexing progress.

## Goals

1. Make indexing non-blocking — `guru index` returns immediately, work runs in background.
2. Auto-index on server startup without blocking request handling.
3. Only re-index files that have actually changed (content-hash-based detection).
4. Watch the file system for changes and re-index automatically.
5. Provide observable job progress (files processed / total, phase, status).
6. Surface job state through `guru status` and a dedicated job endpoint.

## Non-Goals

- Parallel file processing within a single job (future optimization).
- Job persistence across server restarts (restart triggers fresh index).
- Job history size limits (server lifetime is short enough).

---

## Design

### 1. Change Detection: `file_manifest` Table

A new LanceDB table `file_manifest` sits alongside the existing `chunks` table in
`.guru/db`. It tracks per-file indexing state.

**Schema:**

| Column         | Type     | Purpose                                          |
|----------------|----------|--------------------------------------------------|
| `file_path`    | `string` | Relative path from project root (logical primary key) |
| `content_hash` | `string` | SHA-256 hex digest of file content               |
| `mtime`        | `float`  | File modification time (`os.path.getmtime`)      |
| `indexed_at`   | `float`  | Unix timestamp of last successful indexing        |
| `chunk_count`  | `int`    | Number of chunks produced                        |

**Change detection algorithm (per file):**

1. `stat()` the file to get current `mtime`.
2. Look up `file_path` in `file_manifest`.
3. If not found → file is **new**, must index.
4. If found and `mtime` matches stored value → **unchanged**, skip (no hash needed).
5. If found and `mtime` differs → compute SHA-256:
   - If hash matches → **touched but unchanged** (e.g. `touch`), update mtime in manifest, skip.
   - If hash differs → **modified**, must re-index.

**Deletion detection:**

After processing all matched files, query `file_manifest` for entries whose `file_path`
is not in the set of currently matched files. These are files that were deleted or
excluded by config changes. Delete their chunks from `chunks` and their manifest entry.

### 2. Job System

#### Job Model (In-Memory)

```
Job:
  job_id:          str        # UUID4
  job_type:        str        # "index"
  status:          str        # queued | running | completed | failed
  phase:           str | None # discovery | indexing | null
  files_total:     int        # set after discovery phase
  files_processed: int        # incremented during indexing phase
  files_skipped:   int        # unchanged files (detected during discovery)
  files_deleted:   int        # removed-from-disk files cleaned up
  chunks_created:  int        # total new chunks stored
  error:           str | None # error message if failed
  created_at:      datetime
  started_at:      datetime | None
  finished_at:     datetime | None
```

**Lifecycle:** `queued → running (discovery) → running (indexing) → completed | failed`

#### JobRegistry

Lives on `app.state`. Provides:

- `create_job() -> Job` — create a new job in `queued` status.
- `get_job(job_id) -> Job | None` — lookup by ID.
- `current_job() -> Job | None` — return the running/queued job, if any.
- `list_jobs() -> list[Job]` — all jobs in memory.

**Concurrency guard:** Only one indexing job runs at a time. If a new index request
arrives while a job is running, the existing job's ID is returned instead of starting
a duplicate.

#### Execution

Background indexing runs via `asyncio.create_task()` on the FastAPI event loop. The
indexing work is I/O-bound (file reads + Ollama HTTP calls for embedding), which is
the ideal fit for asyncio.

**Two-phase execution:**

1. **Discovery phase:** Scan config rules, glob files, check each against manifest.
   Build lists of files to index, files to skip, files deleted. Set `files_total`
   and `files_skipped`. Transition to indexing phase.

2. **Indexing phase:** For each file needing work:
   - Delete old chunks (if re-indexing).
   - Parse file → chunks.
   - Embed chunks via Ollama.
   - Store chunks in LanceDB.
   - Update `file_manifest` entry (hash, mtime, indexed_at, chunk_count).
   - Increment `files_processed` and `chunks_created`.
   After all files: delete chunks and manifest entries for deleted files, increment
   `files_deleted`. Mark job `completed`.

**Error handling:** If a single file fails, log the error and continue with remaining
files. If a systemic error occurs (Ollama down, LanceDB unavailable), mark the job
as `failed` with the error message.

### 3. Auto-Index on Server Startup

The FastAPI lifespan hook submits an indexing job after preflight checks complete.
The server starts accepting HTTP requests immediately — the index job runs in the
background.

- **First run** (empty DB): No manifest, every file is new. Full index.
- **Subsequent runs** (existing DB): Manifest populated from prior session. Only
  changed/new files re-indexed. Fast for large projects with few changes.

No special-casing. The startup index is a regular job submitted through `JobRegistry`.

### 4. File-System Watching

**Library:** `watchfiles` — async-native, built on Rust's `notify` crate. Handles
macOS FSEvents, Linux inotify. Provides `awatch()` yielding sets of file changes.

**Behavior:**

- Watcher starts after the initial startup index job completes (avoids racing).
- Watches the project root directory recursively.
- Filters events to files matching configured glob rules from `guru.json`.
- Ignores `.guru/` directory and transient patterns (`.swp`, `~`, `.tmp`).
- **Debounce:** Accumulates changes for 2 seconds before triggering re-index.
  Handles editor save storms and bulk operations (`git checkout`, `git pull`).
- Submits a regular indexing job through `JobRegistry`. Same concurrency guard —
  if a job is already running, the changed files are noted but no new job is submitted
  until the current one completes. The next watcher-triggered job will pick up all
  accumulated changes via the manifest diff.

**Lifecycle:**

- Starts after initial index completes (tied to server lifespan).
- Stops on server shutdown.

**New dependency:** `watchfiles` (minimal transitive deps: `anyio`).

### 5. API Changes

#### Modified: `POST /index`

Returns immediately with a job reference.

**Response model: `IndexAccepted`**
```json
{
  "job_id": "abc-123",
  "status": "running",
  "message": "Indexing started"
}
```

If a job is already running:
```json
{
  "job_id": "abc-123",
  "status": "running",
  "message": "Indexing already in progress"
}
```

#### Modified: `GET /status`

Extended with nullable `current_job` field.

**Response model: `StatusOut` (updated)**
```json
{
  "server_running": true,
  "document_count": 12,
  "chunk_count": 87,
  "last_indexed": "2026-04-10T14:30:00",
  "ollama_available": true,
  "model_loaded": true,
  "current_job": {
    "job_id": "abc-123",
    "status": "running",
    "phase": "indexing",
    "files_total": 15,
    "files_processed": 7,
    "files_skipped": 3
  }
}
```

`current_job` is `null` when no job is running.

#### New: `GET /jobs/{job_id}`

Full job details.

**Response model: `JobDetail`**
```json
{
  "job_id": "abc-123",
  "job_type": "index",
  "status": "completed",
  "phase": null,
  "files_total": 15,
  "files_processed": 12,
  "files_skipped": 3,
  "files_deleted": 1,
  "chunks_created": 48,
  "error": null,
  "created_at": "2026-04-10T14:30:00",
  "started_at": "2026-04-10T14:30:00",
  "finished_at": "2026-04-10T14:30:12"
}
```

Returns 404 if `job_id` not found.

### 6. CLI Changes

- **`guru index`** — prints `"Indexing started (job abc-123)"` and returns immediately.
- **`guru status`** — if a job is running, appends progress line:
  `Indexing: 7/15 files processed (3 skipped)`.
- **`guru status --job <id>`** — prints full job detail (all fields).

### 7. Logging

Server logs per-file activity at INFO level:

```
INFO: [job abc-123] Discovery: 15 files matched, 3 unchanged, 12 to index, 1 deleted
INFO: [job abc-123] Indexed docs/guide.md (4 chunks)
INFO: [job abc-123] Indexed docs/api.md (8 chunks)
INFO: [job abc-123] Deleted docs/old.md (removed from disk)
INFO: [job abc-123] Completed: 12 files indexed, 48 chunks created, 1 deleted
```

### 8. Pydantic Types (guru-core)

New and updated models in `guru_core.types`:

- `IndexAccepted` — response for `POST /index` (replaces `IndexOut`)
- `JobSummary` — compact job info for embedding in `StatusOut`
- `JobDetail` — full job info for `GET /jobs/{job_id}`
- `StatusOut` — updated with `current_job: JobSummary | None`

### 9. Package Changes

- **guru-server:** New modules for job registry, change detection, file watcher.
  Modified index endpoint and startup lifespan. New `watchfiles` dependency.
- **guru-core:** Updated Pydantic types. Updated `GuruClient` with `get_job()` method.
- **guru-cli:** Updated `index` and `status` commands. New `--job` flag on status.
- **guru-mcp:** Update MCP tools if they expose indexing (likely just `index_status`
  returning the new `StatusOut` shape).

### 10. BDD Feature Specs

New feature file(s) covering:

- `guru index` returns immediately with job ID.
- Job progresses through phases and reaches `completed`.
- Unchanged files are skipped on re-index.
- Modified files are re-indexed.
- Deleted files are cleaned up.
- `guru status` shows current job progress.
- `GET /jobs/{job_id}` returns full job details.
- Server auto-indexes on startup.
- File watcher triggers re-index on file change.

---

## Dependencies

**New:** `watchfiles` (added to guru-server).

**Existing (unchanged):** LanceDB, FastAPI, httpx, click, Pydantic, Ollama.

## Migration

The `file_manifest` table is created lazily on first index. Existing installations
with a populated `chunks` table but no manifest will do a full re-index on next
server startup — correct behavior since the manifest needs to be populated.

No breaking changes to stored data. The `chunks` table schema is unchanged.
