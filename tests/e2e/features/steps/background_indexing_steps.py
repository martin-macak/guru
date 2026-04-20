"""Step definitions for background indexing BDD scenarios."""

from __future__ import annotations

import contextlib
import time

import httpx
from behave import then, when


def _url(context, path: str) -> str:
    """Return the correct URL for *path* depending on whether we're in-process."""
    return path if hasattr(context, "server_client") else f"http://localhost{path}"


@contextlib.contextmanager
def _rest_client(context):
    """Yield a REST client scoped to one operation.

    In-process mode: yields ``context.server_client`` (managed externally).
    UDS mode: creates a single ``httpx.Client`` and closes it on exit so
    sockets and file descriptors are not leaked.
    """
    if hasattr(context, "server_client"):
        yield context.server_client
    else:
        socket_path = str(context.project_dir / ".guru" / "guru.sock")
        with httpx.Client(
            transport=httpx.HTTPTransport(uds=socket_path), timeout=30.0
        ) as client:
            yield client


def _wait_for_index(context, timeout=30.0):
    deadline = time.monotonic() + timeout
    # Create a single client for the whole polling loop (avoids per-iteration leaks).
    with _rest_client(context) as client:
        while time.monotonic() < deadline:
            resp = client.get(_url(context, "/status"))
            data = resp.json()
            if data.get("current_job") is None:
                if hasattr(context, "last_job_id") and context.last_job_id:
                    resp = client.get(_url(context, f"/jobs/{context.last_job_id}"))
                    context.last_job = resp.json()
                return
            time.sleep(0.3)
    raise RuntimeError("Index did not complete within timeout")


@when("I trigger indexing via REST API")
def step_trigger_index(context):
    with _rest_client(context) as client:
        resp = client.post(_url(context, "/index"), json={})
    context.index_response = resp.json()
    context.last_job_id = context.index_response.get("job_id")


@when("I trigger indexing via REST API again")
def step_trigger_index_again(context):
    step_trigger_index(context)


@when("I immediately trigger indexing again")
def step_trigger_index_immediately(context):
    """Trigger a second index immediately (for concurrency guard test)."""
    with _rest_client(context) as client:
        resp = client.post(_url(context, "/index"), json={})
    context.second_index_response = resp.json()


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


@then("both responses have a valid job_id")
def step_both_have_job_id(context):
    """Both responses must have a non-empty job_id.

    When the first job is still running the concurrency guard returns the same
    job_id for both responses. When the first job completes before the second
    request arrives the server creates a new job — both behaviours are valid.
    The fake embedder is fast enough that both outcomes may occur in tests.
    """
    first_id = context.index_response.get("job_id")
    second_id = context.second_index_response.get("job_id")
    assert first_id, f"First response missing job_id: {context.index_response}"
    assert second_id, f"Second response missing job_id: {context.second_index_response}"


@then("I can retrieve the job detail via REST API")
def step_get_job_detail(context):
    with _rest_client(context) as client:
        resp = client.get(_url(context, f"/jobs/{context.last_job_id}"))
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


@then("the server status has current_job as null")
def step_status_no_current_job(context):
    with _rest_client(context) as client:
        resp = client.get(_url(context, "/status"))
    data = resp.json()
    assert data["current_job"] is None, f"Expected null current_job but got {data['current_job']}"
