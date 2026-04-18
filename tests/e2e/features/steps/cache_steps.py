"""Step definitions for embedding cache BDD scenarios.

Used by tests/e2e/features/worktree_cache.feature. Most of the steps
for cache_cli.feature are handled by the generic `I run "..."` steps
in cli_steps.py — this file only adds cache-observation and file-edit
helpers that require direct access to the REST API and filesystem.
"""

from __future__ import annotations

import time

import httpx
from behave import given, then, when


def _transport(context) -> httpx.HTTPTransport:
    if hasattr(context, "server_client"):
        return context.server_client
    socket_path = str(context.project_dir / ".guru" / "guru.sock")
    return httpx.HTTPTransport(uds=socket_path)


def _latest_completed_job(context) -> dict | None:
    """Fetch the most recently-completed job via the REST API."""
    transport = _transport(context)
    if hasattr(context, "server_client"):
        resp = transport.get("/status")
        assert resp.status_code == 200, f"GET /status failed: {resp.status_code}"
        data = resp.json()
    else:
        with httpx.Client(transport=transport, timeout=5.0) as client:
            resp = client.get("http://localhost/status")
            assert resp.status_code == 200, f"GET /status failed: {resp.status_code}"
            data = resp.json()

    # Extract last_job_* counters from the cache block — populated by
    # guru_server/api/cache.py::_assemble_stats from the registry
    cache = data.get("cache") or {}
    return {
        "last_job_hits": cache.get("last_job_hits"),
        "last_job_misses": cache.get("last_job_misses"),
    }


@given("the first indexing job embedded every chunk from scratch")
def step_first_job_all_misses(context):
    """Sanity check: after the background `Given the knowledge base has been
    indexed` step, the cache reports zero hits (every chunk was new).
    """
    job = _latest_completed_job(context)
    assert job is not None, "No job state reported on /status"
    assert (job["last_job_hits"] or 0) == 0, (
        f"Expected zero cache hits on the first run, got {job['last_job_hits']}"
    )
    assert (job["last_job_misses"] or 0) > 0, (
        f"Expected non-zero cache misses on the first run, got {job['last_job_misses']}"
    )


@when('I append a new section to "{rel_path}"')
def step_append_section(context, rel_path):
    """Append a new markdown section to an existing file. This changes its
    content hash so the indexer re-processes it on next run, while leaving
    earlier chunks byte-identical so they can hit the cache.
    """
    file_path = context.project_dir / rel_path
    assert file_path.is_file(), f"{rel_path} does not exist"
    # Also bump mtime so the indexer's mtime shortcut is bypassed
    new_content = (
        file_path.read_text()
        + "\n\n## Troubleshooting\n\nIf you encounter issues, consult the FAQ.\n"
    )
    file_path.write_text(new_content)
    # Nudge mtime forward by a second to defeat any sub-second mtime check
    import os

    stat = file_path.stat()
    os.utime(file_path, (stat.st_atime + 1, stat.st_mtime + 1))


@when('I run "guru index" and wait for completion')
def step_run_index_and_wait(context):
    """Trigger indexing via REST and wait for the job to finish."""
    from environment import _trigger_and_wait_index

    context.last_job_detail = _trigger_and_wait_index(context)


def _last_job_counters(context) -> tuple[int, int]:
    """Return (hits, misses) from the most recently-completed index job."""
    time.sleep(0.1)  # let the server commit cache state
    detail = getattr(context, "last_job_detail", None)
    if detail is not None:
        return (detail.get("cache_hits", 0) or 0, detail.get("cache_misses", 0) or 0)
    job = _latest_completed_job(context)
    return (job["last_job_hits"] or 0, job["last_job_misses"] or 0)


@then("the most recent index job reports at least one cache hit")
def step_last_job_has_cache_hits(context):
    """The job detail from /jobs/{id} must show a non-zero cache_hits counter."""
    hits, misses = _last_job_counters(context)
    assert hits > 0, (
        f"Expected at least one cache hit after re-indexing with unchanged chunks, "
        f"got hits={hits}, misses={misses}. The cache is not delivering reuse."
    )


@then("the most recent index job reports at least one cache miss")
def step_last_job_has_cache_misses(context):
    """A mixed hit/miss job — the new content should always miss and re-embed."""
    hits, misses = _last_job_counters(context)
    assert misses > 0, (
        f"Expected at least one cache miss for the newly appended section, "
        f"got hits={hits}, misses={misses}. New content should always be a miss."
    )
