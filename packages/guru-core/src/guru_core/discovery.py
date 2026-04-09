from __future__ import annotations

from pathlib import Path


class GuruNotFoundError(Exception):
    pass


def find_guru_root(start: Path) -> Path:
    """Walk up from start looking for a directory containing .guru/.

    Returns the project root (parent of .guru/).
    Raises GuruNotFoundError if no .guru/ directory is found.
    """
    current = start.resolve()
    while True:
        if (current / ".guru").is_dir():
            return current
        parent = current.parent
        if parent == current:
            raise GuruNotFoundError(
                "Not a guru project. Run `guru init` first."
            )
        current = parent
