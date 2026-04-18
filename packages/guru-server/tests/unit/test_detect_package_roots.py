"""Tests for `_detect_package_roots` used at server startup."""

from __future__ import annotations

from pathlib import Path

from guru_server.app import _detect_package_roots


def test_empty_project_returns_root_only(tmp_path: Path):
    roots = _detect_package_roots(tmp_path)
    assert tmp_path.resolve() in [r.resolve() for r in roots]


def test_top_level_package_detected(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text("")
    roots = _detect_package_roots(tmp_path)
    # pkg's parent (tmp_path) is the import root.
    assert tmp_path.resolve() in [r.resolve() for r in roots]


def test_nested_package_still_rooted_at_parent_of_top_package(tmp_path: Path):
    """src/pkg/sub/__init__.py + src/pkg/__init__.py → src/ is the root."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pkg").mkdir()
    (tmp_path / "src" / "pkg" / "sub").mkdir()
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "sub" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "sub" / "leaf.py").write_text("")
    roots = _detect_package_roots(tmp_path)
    # We want `src/` as the import root — qualname of leaf.py becomes `pkg.sub.leaf`.
    assert (tmp_path / "src").resolve() in [r.resolve() for r in roots]


def test_skips_venv_and_node_modules(tmp_path: Path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pkg").mkdir()
    (tmp_path / ".venv" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "__init__.py").write_text("")
    roots = _detect_package_roots(tmp_path)
    for r in roots:
        assert ".venv" not in r.parts
        assert "node_modules" not in r.parts
