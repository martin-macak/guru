from __future__ import annotations

from pathlib import Path

import yaml


def _load_ci_workflow() -> dict:
    return yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))


def _job_step(job: dict, name: str) -> dict:
    for step in job["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing step {name!r}")


def test_e2e_job_provisions_neo4j_service():
    job = _load_ci_workflow()["jobs"]["e2e-tests"]

    assert job["services"]["neo4j"]["image"] == "neo4j:5"
    assert job["services"]["neo4j"]["env"]["NEO4J_AUTH"] == "none"


def test_e2e_job_passes_external_bolt_uri_to_behave():
    job = _load_ci_workflow()["jobs"]["e2e-tests"]
    step = _job_step(job, "Run BDD e2e tests")

    assert step["env"]["GURU_NEO4J_BOLT_URI"] == "bolt://localhost:7687"
