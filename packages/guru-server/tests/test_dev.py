from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """A minimal project directory with .guru/ and .guru.json."""
    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    (tmp_path / ".guru.json").write_text(
        json.dumps({"version": 1, "name": "test-project", "rules": []})
    )
    return tmp_path


def test_create_dev_app_returns_fastapi_app(project_dir: Path, monkeypatch):
    """create_dev_app returns a FastAPI app usable by uvicorn."""
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))

    from fastapi import FastAPI

    from guru_server.dev import create_dev_app

    app = create_dev_app()
    assert isinstance(app, FastAPI)


def test_create_dev_app_mounts_api_router(project_dir: Path, monkeypatch):
    """create_dev_app mounts the top-level API routes including /web/boot."""
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))

    from guru_server.dev import create_dev_app

    app = create_dev_app()
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/web/boot" in paths
    assert "/status" in paths


def test_create_dev_app_raises_when_guru_dir_missing(tmp_path: Path, monkeypatch):
    """create_dev_app raises RuntimeError if .guru/ does not exist."""
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(tmp_path / "cache.db"))

    from guru_server.dev import create_dev_app

    with pytest.raises(RuntimeError, match=r"\.guru"):
        create_dev_app()


def test_resolve_reload_dirs_returns_absolute_paths_for_known_packages():
    """Returns absolute paths to guru-server, guru-core, guru-graph src dirs."""
    from guru_server.dev import _resolve_reload_dirs

    dirs = _resolve_reload_dirs()
    names = [Path(p).parent.name for p in dirs]  # .../packages/<pkg>/src
    assert "guru-server" in names
    assert "guru-core" in names
    assert "guru-graph" in names
    for p in dirs:
        assert Path(p).is_absolute()
        assert Path(p).is_dir()
