"""Installer for the guru-knowledge-base skill."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

# The skill assets ship under ``guru_cli/assets/skills/guru-knowledge-base/``.
# The directory name contains a hyphen, which is not a valid Python identifier,
# so we cannot pass it as a dotted module path to ``resources.files``. Instead
# we resolve the parent package (which IS a Python module via ``__init__.py``)
# and traverse into the hyphenated subdirectory using the Traversable interface.
_PKG_PARENT = "guru_cli.assets.skills"
_SKILL_DIRNAME = "guru-knowledge-base"


def _asset_root() -> Path:
    parent = resources.files(_PKG_PARENT)
    skill = parent / _SKILL_DIRNAME
    # In a normal (extracted) install this is already a real filesystem path.
    # ``as_file`` would be required for zipped wheels, but the directory tree
    # would also need to be materialised as a whole — we keep the simple path
    # here and let the Traversable interface degrade gracefully.
    return Path(str(skill))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_paths(root: Path) -> list[Path]:
    files = ["SKILL.md"]
    for n in ("model", "discovery", "curation", "annotation-shape", "linking-patterns", "orphans"):
        files.append(f"references/{n}.md")
    return [Path(f) for f in files]


def _copy_tree_preserving_paths(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for rel in _manifest_paths(src):
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((src / rel).read_bytes())


def _write_manifest(dst: Path, shipped_hashes: dict[str, str], guru_version: str) -> None:
    manifest = {
        "guru_version": guru_version,
        "files": shipped_hashes,
    }
    (dst / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))


def _agents_symlink_or_copy(claude_path: Path, agents_path: Path) -> None:
    agents_path.parent.mkdir(parents=True, exist_ok=True)
    if agents_path.exists() or agents_path.is_symlink():
        return
    if sys.platform == "win32":
        shutil.copytree(claude_path, agents_path)
    else:
        # Relative symlink from .agents/skills/guru-knowledge-base to .claude/skills/guru-knowledge-base
        rel = os.path.relpath(claude_path, agents_path.parent)
        agents_path.symlink_to(rel)


def install_skill(project_root: Path, *, guru_version: str = "0.0.0") -> list[str]:
    """Materialise the skill tree under .claude/skills/guru-knowledge-base and mirror to .agents/."""
    src = _asset_root()
    claude_dest = project_root / ".claude" / "skills" / "guru-knowledge-base"
    _copy_tree_preserving_paths(src, claude_dest)
    shipped_hashes = {
        str(rel): _sha256_bytes((src / rel).read_bytes()) for rel in _manifest_paths(src)
    }
    _write_manifest(claude_dest, shipped_hashes, guru_version)
    _agents_symlink_or_copy(
        claude_dest,
        project_root / ".agents" / "skills" / "guru-knowledge-base",
    )
    return list(shipped_hashes)


def update_skill(
    project_root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    src = _asset_root()
    dest = project_root / ".claude" / "skills" / "guru-knowledge-base"
    if not dest.exists():
        return install_skill(project_root)

    manifest_path = dest / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    manifest_hashes: dict[str, str] = manifest.get("files", {})

    changed: list[str] = []
    ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")

    new_hashes: dict[str, str] = {}
    for rel in _manifest_paths(src):
        rel_s = str(rel)
        shipped_bytes = (src / rel).read_bytes()
        shipped_h = _sha256_bytes(shipped_bytes)
        new_hashes[rel_s] = shipped_h

        user_path = dest / rel
        user_h = _sha256_bytes(user_path.read_bytes()) if user_path.exists() else None
        manifest_h = manifest_hashes.get(rel_s)

        if user_h == shipped_h:
            # File content already matches shipped. If the recorded manifest
            # hash is stale, surface this as "changed" so the manifest gets
            # rewritten — but never touch the file itself.
            if manifest_h != shipped_h:
                changed.append(rel_s)
            continue
        if user_h is None:
            # Missing on disk; reinstall it
            changed.append(rel_s)
            if not dry_run:
                user_path.parent.mkdir(parents=True, exist_ok=True)
                user_path.write_bytes(shipped_bytes)
            continue
        if user_h == manifest_h:
            # Unmodified by user, shipped changed -> safe overwrite
            changed.append(rel_s)
            if not dry_run:
                user_path.write_bytes(shipped_bytes)
        else:
            # User customised
            if force:
                backup = user_path.with_name(f"{user_path.name}.bak.{ts}")
                if not dry_run:
                    shutil.copy2(user_path, backup)
                    user_path.write_bytes(shipped_bytes)
                changed.append(rel_s)

    if changed and not dry_run:
        _write_manifest(dest, new_hashes, guru_version=manifest.get("guru_version", "0.0.0"))
    return changed
