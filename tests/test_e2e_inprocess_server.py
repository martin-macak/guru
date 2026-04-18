from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
import time
from pathlib import Path

import pytest

_ENVIRONMENT_PATH = Path(__file__).resolve().parent / "e2e" / "features" / "environment.py"
_ENVIRONMENT_SPEC = importlib.util.spec_from_file_location(
    "tests_e2e_features_environment", _ENVIRONMENT_PATH
)
assert _ENVIRONMENT_SPEC is not None and _ENVIRONMENT_SPEC.loader is not None
environment = importlib.util.module_from_spec(_ENVIRONMENT_SPEC)
sys.modules[_ENVIRONMENT_SPEC.name] = environment
_ENVIRONMENT_SPEC.loader.exec_module(environment)


@pytest.fixture
def standard_project():
    project_dir = environment._create_standard_project()
    try:
        yield project_dir
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)


def test_start_inprocess_server_exposes_status(standard_project):
    server_client, guru_client = environment._start_inprocess_server(
        standard_project, environment._make_fake_embedder()
    )
    try:
        status = asyncio.run(guru_client.status())
    finally:
        server_client.__exit__(None, None, None)

    assert status["server_running"] is True
    assert status["chunk_count"] == 0


def test_inprocess_guru_client_can_index_and_query_documents(standard_project):
    server_client, guru_client = environment._start_inprocess_server(
        standard_project, environment._make_fake_embedder()
    )
    try:
        job = asyncio.run(guru_client.trigger_index())
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            status = asyncio.run(guru_client.status())
            if status.get("current_job") is None and status["chunk_count"] > 0:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("index job did not complete in time")

        docs = asyncio.run(guru_client.list_documents())
    finally:
        server_client.__exit__(None, None, None)

    assert "job_id" in job
    assert any(doc["file_path"].endswith("auth.md") for doc in docs)
