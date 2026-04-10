from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from guru_core.types import Rule

logger = logging.getLogger(__name__)

TRANSIENT_SUFFIXES = {".swp", ".swo", ".tmp", "~"}
DEBOUNCE_SECONDS = 2.0


def should_watch_path(path: Path, project_root: Path, config: list[Rule]) -> bool:
    """Check if a changed path should trigger re-indexing."""
    # Ignore paths outside project root
    try:
        rel = path.relative_to(project_root)
    except ValueError:
        return False

    # Ignore .guru/ directory
    if rel.parts and rel.parts[0] == ".guru":
        return False

    # Ignore transient editor files
    name = path.name
    if any(name.endswith(s) for s in TRANSIENT_SUFFIXES):
        return False
    if name.startswith(".") and name.endswith(".tmp"):
        return False

    # Check if file matches any include glob using regex conversion
    # (PurePosixPath.match("docs/**/*.md") won't match "docs/file.md" directly)
    str_rel = str(rel)
    matched = False
    excluded = False

    for rule in config:
        if _glob_matches(rule.match.glob, str_rel):
            if rule.exclude:
                excluded = True
            else:
                matched = True

    return matched and not excluded


def _glob_matches(pattern: str, path: str) -> bool:
    """Match a glob pattern against a relative path string.

    Supports ``**`` for zero-or-more directory components, matching
    both ``docs/guide.md`` and ``docs/sub/guide.md`` against ``docs/**/*.md``.
    """
    regex = re.escape(pattern)
    # **/ → zero or more directory components (including zero)
    regex = regex.replace(r"\*\*/", "(.*/)?")
    # remaining * → any non-separator characters
    regex = regex.replace(r"\*", "[^/]*")
    return bool(re.fullmatch(regex, path))


async def start_watcher(
    project_root: Path,
    config: list[Rule],
    job_registry,
    submit_index,
) -> None:
    """Watch project files for changes and trigger re-indexing.

    Args:
        project_root: The project root directory to watch.
        config: The indexing config rules for filtering.
        job_registry: The job registry to check for running jobs.
        submit_index: Async callable to submit a new indexing job.
    """
    from watchfiles import awatch

    logger.info("File watcher started on %s", project_root)

    try:
        async for changes in awatch(project_root, debounce=int(DEBOUNCE_SECONDS * 1000)):
            # Filter to relevant changes
            relevant = [
                path
                for _change_type, path in changes
                if should_watch_path(Path(path), project_root, config)
            ]

            if not relevant:
                continue

            logger.info("File watcher detected %d relevant change(s)", len(relevant))

            # Check if a job is already running
            if job_registry.current_job() is not None:
                logger.info("Index job already running, changes will be picked up by next run")
                continue

            await submit_index()
    except asyncio.CancelledError:
        logger.info("File watcher stopped")
        raise
    except Exception:
        logger.exception("File watcher error")
