"""Step definitions for knowledge base CLI scenarios."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from behave import given, when, then


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], cwd: Path) -> tuple[int, str]:
    """Invoke the guru CLI in the given working directory."""
    result = subprocess.run(
        ["uv", "run", "guru", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=os.environ.copy(),
        timeout=30,
    )
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# GIVEN steps
# ---------------------------------------------------------------------------


@given("a guru project with sample markdown files")
def step_project_exists(context):
    """Project dir is created in environment.py before_feature."""
    assert context.project_dir.exists(), "Project directory was not created"
    assert (context.project_dir / ".guru").is_dir(), ".guru/ does not exist"
    assert (context.project_dir / "guru.json").is_file(), "guru.json does not exist"


@given("the guru server is running")
def step_server_running(context):
    """Server is started in environment.py before_feature."""
    sock = context.project_dir / ".guru" / "guru.sock"
    assert sock.exists(), f"Server socket not found at {sock}"


@given("the knowledge base has been indexed")
def step_index_kb(context):
    """Run index once so subsequent steps have data."""
    code, out = _run_cli(["index"], cwd=context.project_dir)
    assert code == 0, f"Indexing failed:\n{out}"
    context.last_exit_code = code
    context.last_output = out


# ---------------------------------------------------------------------------
# WHEN steps
# ---------------------------------------------------------------------------


@when('I run "{command}"')
def step_run_command(context, command):
    """Run a guru CLI command, substituting {picked_path} if present."""
    if "{picked_path}" in command and hasattr(context, "picked_path"):
        command = command.replace("{picked_path}", context.picked_path)

    parts = command.split()
    assert parts[0] == "guru", f"Expected 'guru' command, got: {parts[0]}"
    args = parts[1:]

    code, out = _run_cli(args, cwd=context.project_dir)
    context.last_exit_code = code
    context.last_output = out


@when('I search for "{query}"')
def step_search(context, query):
    """Run guru search with a multi-word query."""
    code, out = _run_cli(["search", query], cwd=context.project_dir)
    context.last_exit_code = code
    context.last_output = out


@when('I list documents and pick the path containing "{fragment}"')
def step_list_and_pick(context, fragment):
    """Run guru list and extract the file path containing the fragment."""
    code, out = _run_cli(["list"], cwd=context.project_dir)
    assert code == 0, f"List failed:\n{out}"

    for line in out.splitlines():
        if fragment in line:
            context.picked_path = line.strip().split(" ")[0]
            return

    assert False, f"'{fragment}' not found in list output:\n{out}"


# ---------------------------------------------------------------------------
# THEN steps
# ---------------------------------------------------------------------------


@then("the command succeeds")
def step_command_succeeds(context):
    assert context.last_exit_code == 0, (
        f"Command failed (exit {context.last_exit_code}):\n{context.last_output}"
    )


@then('the output contains "{text}"')
def step_output_contains(context, text):
    assert text in context.last_output, (
        f"Expected '{text}' in output:\n{context.last_output}"
    )


@then('the output does not contain "{text}"')
def step_output_not_contains(context, text):
    assert text not in context.last_output, (
        f"Did not expect '{text}' in output:\n{context.last_output}"
    )
