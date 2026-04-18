"""Step definitions for knowledge base CLI scenarios."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when
from click.testing import CliRunner

from guru_cli.cli import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(context, args: list[str], cwd: Path) -> tuple[int, str]:
    """Invoke the guru CLI in the given working directory."""
    if hasattr(context, "guru_client"):
        runner = CliRunner()
        old_cwd = Path.cwd()
        try:
            os.chdir(cwd)
            with patch("guru_cli.cli._get_client", return_value=context.guru_client):
                result = runner.invoke(cli, args)
        finally:
            os.chdir(old_cwd)
        return result.exit_code, result.output

    result = subprocess.run(
        ["uv", "run", "guru", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=os.environ.copy(),
        timeout=60,
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
    assert (context.project_dir / ".guru.json").is_file(), ".guru.json does not exist"


@given("a guru project with topically distinct documents")
def step_semantic_project_exists(context):
    """Semantic project dir is created in environment.py before_feature."""
    assert context.project_dir.exists(), "Project directory was not created"
    assert (context.project_dir / "guides").is_dir(), "guides/ does not exist"
    assert (context.project_dir / "references").is_dir(), "references/ does not exist"
    assert (context.project_dir / "notes").is_dir(), "notes/ does not exist"


@given("the guru server is running")
def step_server_running(context):
    """Server is started in environment.py before_feature."""
    if hasattr(context, "server_client"):
        assert context.server_client is not None, "In-process server client was not created"
        return
    sock = context.project_dir / ".guru" / "guru.sock"
    assert sock.exists(), f"Server socket not found at {sock}"


@given("the guru server is running with real embeddings")
def step_server_running_real(context):
    """Server with real Ollama is started in environment.py before_feature."""
    if hasattr(context, "server_client"):
        assert context.server_client is not None, "In-process server client was not created"
        return
    sock = context.project_dir / ".guru" / "guru.sock"
    assert sock.exists(), f"Server socket not found at {sock}"


@given("the knowledge base has been indexed")
def step_index_kb(context):
    """Index the knowledge base via REST API and wait for completion."""
    from environment import _trigger_and_wait_index

    _trigger_and_wait_index(context)


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

    code, out = _run_cli(context, args, cwd=context.project_dir)
    context.last_exit_code = code
    context.last_output = out


@when('I search for "{query}"')
def step_search(context, query):
    """Run guru search with a multi-word query."""
    code, out = _run_cli(context, ["search", query], cwd=context.project_dir)
    context.last_exit_code = code
    context.last_output = out


@when('I list documents and pick the path containing "{fragment}"')
def step_list_and_pick(context, fragment):
    """Run guru list and extract the file path containing the fragment."""
    code, out = _run_cli(context, ["list"], cwd=context.project_dir)
    assert code == 0, f"List failed:\n{out}"

    for line in out.splitlines():
        if fragment in line:
            context.picked_path = line.strip().split(" ")[0]
            return

    raise AssertionError(f"'{fragment}' not found in list output:\n{out}")


@when('I get the document containing "{fragment}"')
def step_get_doc_containing(context, fragment):
    """List documents, find one matching fragment, and get its full JSON."""
    code, list_out = _run_cli(context, ["list"], cwd=context.project_dir)
    assert code == 0, f"List failed:\n{list_out}"

    doc_path = None
    for line in list_out.splitlines():
        if fragment in line:
            doc_path = line.strip().split(" ")[0]
            break
    assert doc_path is not None, f"No document containing '{fragment}' in list output:\n{list_out}"

    code, out = _run_cli(context, ["doc", doc_path], cwd=context.project_dir)
    context.last_exit_code = code
    context.last_output = out


# ---------------------------------------------------------------------------
# THEN steps
# ---------------------------------------------------------------------------


@then("the command succeeds")
def step_command_succeeds(context):
    assert context.last_exit_code == 0, (
        f"Command failed (exit {context.last_exit_code}):\n{context.last_output}"
    )


@then("the command fails")
def step_command_fails(context):
    assert context.last_exit_code != 0, (
        f"Command unexpectedly succeeded (exit 0):\n{context.last_output}"
    )


@then('the output contains "{text}"')
def step_output_contains(context, text):
    assert text in context.last_output, f"Expected '{text}' in output:\n{context.last_output}"


@then('the output does not contain "{text}"')
def step_output_not_contains(context, text):
    assert text not in context.last_output, (
        f"Did not expect '{text}' in output:\n{context.last_output}"
    )


@then('the first result contains "{alternatives}"')
def step_first_result_contains_alternatives(context, alternatives):
    """Check that the first search result contains at least one of the words.

    alternatives is a string like: cooking" or "recipe" or "ingredient
    (behave parses the outer quotes, inner quotes are literal)
    """
    keywords = [w.strip().strip('"') for w in alternatives.split(" or ")]

    # Extract the first result block from the search output
    lines = context.last_output.splitlines()
    first_block = []
    in_result = False
    for line in lines:
        if "--- Result 1" in line:
            in_result = True
            continue
        if in_result and "--- Result 2" in line:
            break
        if in_result:
            first_block.append(line)

    first_text = "\n".join(first_block).lower()
    assert first_text, f"No Result 1 found in output:\n{context.last_output}"

    matched = [kw for kw in keywords if kw.lower() in first_text]
    assert matched, (
        f"First result does not contain any of {keywords}.\nFirst result text:\n{first_text}"
    )


@then('the document has label "{label}"')
def step_doc_has_label(context, label):
    """Verify the JSON output from 'guru doc' contains the expected label."""
    assert label in context.last_output, (
        f"Label '{label}' not found in document output:\n{context.last_output}"
    )


@then('the search results contain label "{label}"')
def step_search_results_contain_label(context, label):
    """Verify the search output contains the label somewhere.

    Labels are returned as a list in search results. The CLI search command
    doesn't explicitly display labels, so we check via 'guru doc' on the
    first result's file path.
    """
    # Extract file path from the first search result
    file_path = None
    for line in context.last_output.splitlines():
        if line.startswith("File:"):
            file_path = line.replace("File:", "").strip()
            break

    assert file_path is not None, f"No file path found in search output:\n{context.last_output}"

    # Get the document JSON and check label
    code, out = _run_cli(context, ["doc", file_path], cwd=context.project_dir)
    assert code == 0, f"Failed to get doc {file_path}:\n{out}"
    assert label in out, f"Label '{label}' not found in document for {file_path}:\n{out}"
