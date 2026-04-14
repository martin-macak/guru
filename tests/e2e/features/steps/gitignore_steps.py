"""Step definitions for gitignore-aware discovery BDD tests.

Used by tests/e2e/features/gitignore_discovery.feature. The project
fixture itself is created in environment.py::_create_gitignore_project
when a feature carries the @gitignore_project tag; these steps just
verify its preconditions.
"""

from __future__ import annotations

from behave import given


@given("a guru project inside a git repository")
def step_gitignore_project_exists(context):
    """The @gitignore_project fixture set up the project in before_feature."""
    assert context.project_dir.exists(), "Project directory was not created"
    assert (context.project_dir / ".git").is_dir(), (
        "Project is not a git repo — @gitignore_project tag must be set"
    )
    assert (context.project_dir / ".gitignore").is_file(), ".gitignore is missing"
    assert (context.project_dir / ".guru.json").is_file(), ".guru.json is missing"
    assert (context.project_dir / "docs" / "real.md").is_file(), "docs/real.md missing"
    assert (context.project_dir / "node_modules" / "README.md").is_file(), (
        "node_modules/README.md missing — can't verify it gets skipped"
    )
