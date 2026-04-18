"""Step defs for tests/e2e/features/skill_distribution.feature.

Drives `guru init` and `guru update` via Click's CliRunner against a
per-scenario tmpdir. No guru-server / graph daemon required.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from behave import given, then, when
from click.testing import CliRunner

from guru_cli.cli import cli as guru_cli_root

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill_dir(context) -> Path:
    return Path(context.tmp_project) / ".claude" / "skills" / "guru-knowledge-base"


def _run_guru(context, *args: str):
    """Invoke `guru …` against context.tmp_project. Stores result on context.

    Sets both ``context.cli_result`` (CliRunner Result) and the shared
    ``context.cli_out`` attribute so the shared ``stdout contains`` step
    defined in graph_optional_steps.py can be reused.
    """
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(context.tmp_project)
    try:
        context.cli_result = runner.invoke(guru_cli_root, list(args), catch_exceptions=False)
    finally:
        os.chdir(cwd)
    context.cli_out = context.cli_result.output
    context.cli_exit = context.cli_result.exit_code


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given("a fresh tmpdir project")
def step_fresh_tmpdir(context):
    context.tmp_project = tempfile.mkdtemp(prefix="g_skill_")
    context.add_cleanup(lambda: shutil.rmtree(context.tmp_project, ignore_errors=True))


@given("the skill was just installed in a tmpdir project")
@given("the skill was installed in a tmpdir project")
def step_skill_installed(context):
    step_fresh_tmpdir(context)
    _run_guru(context, "init")
    assert context.cli_result.exit_code == 0, context.cli_result.output
    # Snapshot mtimes + hashes for later "no files modified" assertion.
    context.installed_state = {
        p: (p.stat().st_mtime_ns, _hash_file(p))
        for p in _skill_dir(context).rglob("*")
        if p.is_file()
    }


@given('the MANIFEST.json hash for "{name}" was tampered to look stale')
def step_tamper_manifest(context, name):
    manifest_path = _skill_dir(context) / "MANIFEST.json"
    m = json.loads(manifest_path.read_text())
    m["files"][name] = "deadbeef" * 8
    manifest_path.write_text(json.dumps(m))


@given('the user has edited "{name}" in the project')
def step_user_edits(context, name):
    target = _skill_dir(context) / name
    target.write_text(target.read_text() + "\n\n## User addition\n")


@given('the user has edited "{name}" in the project with content "{content}"')
def step_user_edits_with_content(context, name, content):
    # Behave un-escapes \n in the table; literal "\n" stays literal in feature
    # text. Decode the common case so tests behave intuitively.
    target = _skill_dir(context) / name
    target.write_text(content.replace("\\n", "\n"))


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when('I run skill command "{cmd}"')
def step_run_skill_cmd(context, cmd):
    parts = cmd.split()
    assert parts[0] == "guru", f"expected `guru ...`, got {cmd!r}"
    _run_guru(context, *parts[1:])


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


@then('".claude/skills/guru-knowledge-base/SKILL.md" exists in the project')
def step_skill_md_exists(context):
    p = _skill_dir(context) / "SKILL.md"
    assert p.exists(), f"missing: {p}"


@then('all six reference files exist under ".claude/skills/guru-knowledge-base/references/"')
def step_six_refs_exist(context):
    refs_dir = _skill_dir(context) / "references"
    expected = {
        "model.md",
        "discovery.md",
        "curation.md",
        "annotation-shape.md",
        "linking-patterns.md",
        "orphans.md",
    }
    found = {p.name for p in refs_dir.glob("*.md")}
    missing = expected - found
    assert not missing, f"missing reference files: {missing}"


@then('".agents/skills/guru-knowledge-base" is a symlink (or directory copy) to the .claude path')
def step_agents_mirror(context):
    agents = Path(context.tmp_project) / ".agents" / "skills" / "guru-knowledge-base"
    assert agents.exists() or agents.is_symlink(), f"missing: {agents}"


@then('"MANIFEST.json" contains a sha256 for every shipped file')
def step_manifest_complete(context):
    manifest_path = _skill_dir(context) / "MANIFEST.json"
    m = json.loads(manifest_path.read_text())
    files = m.get("files", {})
    expected = {"SKILL.md"} | {
        f"references/{n}.md"
        for n in (
            "model",
            "discovery",
            "curation",
            "annotation-shape",
            "linking-patterns",
            "orphans",
        )
    }
    missing = expected - set(files.keys())
    assert not missing, f"manifest missing entries: {missing}"
    for name, h in files.items():
        assert isinstance(h, str) and len(h) == 64, f"{name}: not a sha256 ({h!r})"


@then('no files under ".claude/skills/guru-knowledge-base/" are modified')
def step_no_files_modified(context):
    """Compare to the snapshot taken in step_skill_installed."""
    for p, (_mtime0, hash0) in context.installed_state.items():
        assert p.exists(), f"file vanished: {p}"
        assert _hash_file(p) == hash0, f"file changed: {p}"


@then('"{name}" appears in the update output')
def step_name_in_output(context, name):
    assert name in context.cli_result.output, f"expected {name!r} in:\n{context.cli_result.output}"


@then("MANIFEST.json is refreshed")
def step_manifest_refreshed(context):
    """The tampered hash should be replaced by the real shipped hash."""
    manifest_path = _skill_dir(context) / "MANIFEST.json"
    m = json.loads(manifest_path.read_text())
    skill_path = _skill_dir(context) / "SKILL.md"
    real_h = _hash_file(skill_path)
    assert m["files"]["SKILL.md"] == real_h, "MANIFEST.json was not refreshed"


@then('"{name}" was not overwritten')
def step_not_overwritten(context, name):
    """The user's edit (appended content) should still be present."""
    p = _skill_dir(context) / name
    assert "## User addition" in p.read_text(), f"{name} was overwritten"


@then("exit code is {code:d}")
def step_exit_code(context, code):
    assert context.cli_result.exit_code == code, (
        f"expected exit code {code}, got {context.cli_result.exit_code}: {context.cli_result.output}"
    )


@then('a "{pattern}" file exists with the previous user content')
def step_backup_exists(context, pattern):
    """`pattern` is like "SKILL.md.bak.<timestamp>" — match by glob prefix."""
    base = pattern.split(".bak.")[0]
    skill_dir = _skill_dir(context)
    backups = list(skill_dir.glob(f"{base}.bak.*"))
    assert len(backups) == 1, f"expected exactly 1 backup for {base!r}, got {backups}"
    # The implementer's "user-customised\n" content from the previous step.
    assert backups[0].read_text() == "user-customised\n", (
        f"backup content unexpected: {backups[0].read_text()!r}"
    )


@then('"{name}" matches the shipped version')
def step_matches_shipped(context, name):
    """Compare to the asset shipped in the wheel."""
    from importlib import resources

    parent = resources.files("guru_cli.assets.skills")
    shipped_bytes = (Path(str(parent)) / "guru-knowledge-base" / name).read_bytes()
    on_disk = _skill_dir(context) / name
    assert on_disk.read_bytes() == shipped_bytes, f"{name} does not match shipped version"


@then('"{name}" output line starts with "{prefix}"')
def step_output_line_prefix(context, name, prefix):
    """Find a line in stdout starting with prefix and containing name."""
    for line in context.cli_result.output.splitlines():
        if line.startswith(prefix) and name in line:
            return
    raise AssertionError(
        f"no line starts with {prefix!r} and mentions {name!r}:\n{context.cli_result.output}"
    )


@then("the SKILL.md mtime did not change")
def step_mtime_unchanged(context):
    p = _skill_dir(context) / "SKILL.md"
    mtime0, _hash0 = context.installed_state[p]
    assert p.stat().st_mtime_ns == mtime0, "SKILL.md was rewritten"
