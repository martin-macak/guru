#!/usr/bin/env python3
"""Generate a PEP 503 simple repository index from a directory of wheels.

Usage: python scripts/generate-index.py <wheels-dir> <output-dir>

Scans <wheels-dir> for .whl files and generates a PEP 503-compliant simple
repository index in <output-dir>/. Package directories use normalized names
(lowercase, hyphens). Links point to ../../wheels/<filename>.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# PEP 503: normalize by lowercasing and replacing runs of [_.-] with a single hyphen
_NORMALIZE_RE = re.compile(r"[-_.]+")


def _normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("-", name).lower()


def _parse_wheel_name(filename: str) -> str | None:
    """Extract the distribution name from a wheel filename.

    Wheel filenames follow: {name}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    """
    parts = filename.split("-")
    if len(parts) < 3:
        return None
    return parts[0]


def generate_index(wheels_dir: Path, output_dir: Path) -> None:
    """Generate PEP 503 simple index from wheels directory."""
    wheel_files = sorted(wheels_dir.glob("*.whl"))

    # Group wheels by normalized package name
    packages: dict[str, list[str]] = {}
    for whl in wheel_files:
        raw_name = _parse_wheel_name(whl.name)
        if raw_name is None:
            continue
        norm = _normalize(raw_name)
        packages.setdefault(norm, []).append(whl.name)

    # Generate root index
    output_dir.mkdir(parents=True, exist_ok=True)
    root_links = []
    for name in sorted(packages):
        root_links.append(f'<a href="{name}/">{name}</a>')

    (output_dir / "index.html").write_text(
        "<!DOCTYPE html>\n<html><body>\n" + "\n".join(root_links) + "\n</body></html>\n"
    )

    # Generate per-package index
    for name, wheels in sorted(packages.items()):
        pkg_dir = output_dir / name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        links = []
        for whl in sorted(wheels):
            links.append(f'<a href="../../wheels/{whl}">{whl}</a>')
        (pkg_dir / "index.html").write_text(
            "<!DOCTYPE html>\n<html><body>\n" + "\n".join(links) + "\n</body></html>\n"
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <wheels-dir> <output-dir>", file=sys.stderr)
        sys.exit(1)
    generate_index(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"Index generated in {sys.argv[2]}")
