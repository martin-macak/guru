"""`guru update` — refresh guru-managed artefacts in the current project."""

from __future__ import annotations

from pathlib import Path

import click

from guru_cli.skills_install import update_skill


@click.command("update")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite user-customised files (originals saved as <name>.bak.<timestamp>).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Report what would change without writing.",
)
def update_cmd(force: bool, dry_run: bool) -> None:
    """Refresh guru-managed assets (currently: the knowledge-base skill).

    Reads the local MANIFEST.json under .claude/skills/guru-knowledge-base/
    and reconciles each shipped file:

    - Shipped == user → no-op.
    - Shipped changed, user matches manifest → safe overwrite + manifest refresh.
    - Shipped changed, user diverges → skip (use --force to overwrite + back up).
    """
    project_root = Path.cwd()
    changed = update_skill(project_root, force=force, dry_run=dry_run)
    if not changed:
        click.echo("already up to date")
        return
    prefix = "would update" if dry_run else "updated"
    for rel in changed:
        click.echo(f"{prefix}: {rel}")
