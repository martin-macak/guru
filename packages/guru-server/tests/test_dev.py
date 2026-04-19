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


def test_main_invokes_uvicorn_with_reload_factory_and_port(project_dir: Path, monkeypatch):
    """main() configures uvicorn.run with factory=True, reload=True, pinned port."""
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))
    monkeypatch.setenv("GURU_DEV_PORT", "9999")

    import guru_server.dev as dev_mod

    monkeypatch.setattr(dev_mod, "check_ollama_installed", lambda: None)
    monkeypatch.setattr(dev_mod, "start_ollama_serve", lambda: None)
    monkeypatch.setattr(dev_mod, "stop_ollama_serve", lambda proc: None)
    monkeypatch.setattr(dev_mod, "check_model_available", lambda model: None)

    captured: dict = {}

    def fake_run(app_ref, **kwargs):
        captured["app_ref"] = app_ref
        captured["kwargs"] = kwargs

    monkeypatch.setattr(dev_mod.uvicorn, "run", fake_run)

    dev_mod.main([])

    assert captured["app_ref"] == "guru_server.dev:create_dev_app"
    assert captured["kwargs"]["factory"] is True
    assert captured["kwargs"]["reload"] is True
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 9999
    # reload_dirs should contain absolute paths
    assert all(Path(p).is_absolute() for p in captured["kwargs"]["reload_dirs"])


def test_main_defaults_port_to_8765(project_dir: Path, monkeypatch):
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))
    monkeypatch.delenv("GURU_DEV_PORT", raising=False)

    import guru_server.dev as dev_mod

    monkeypatch.setattr(dev_mod, "check_ollama_installed", lambda: None)
    monkeypatch.setattr(dev_mod, "start_ollama_serve", lambda: None)
    monkeypatch.setattr(dev_mod, "stop_ollama_serve", lambda proc: None)
    monkeypatch.setattr(dev_mod, "check_model_available", lambda model: None)

    captured: dict = {}
    monkeypatch.setattr(
        dev_mod.uvicorn,
        "run",
        lambda app_ref, **kw: captured.update(kw),
    )

    dev_mod.main([])
    assert captured["port"] == 8765


def test_main_stops_ollama_only_if_started(project_dir: Path, monkeypatch):
    """If start_ollama_serve returns None (already running), stop_ollama_serve
    must still be called with None — the existing helper is a no-op on None."""
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))

    import guru_server.dev as dev_mod

    monkeypatch.setattr(dev_mod, "check_ollama_installed", lambda: None)
    monkeypatch.setattr(dev_mod, "start_ollama_serve", lambda: None)
    monkeypatch.setattr(dev_mod, "check_model_available", lambda model: None)
    monkeypatch.setattr(dev_mod.uvicorn, "run", lambda app_ref, **kw: None)

    stopped: list = []
    monkeypatch.setattr(dev_mod, "stop_ollama_serve", lambda proc: stopped.append(proc))

    dev_mod.main([])
    assert stopped == [None]


def test_main_exits_when_guru_dir_missing(tmp_path: Path, monkeypatch, capsys):
    """Missing .guru/ causes main() to sys.exit(1) with an actionable message."""
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(tmp_path))  # no .guru/ subdir

    import guru_server.dev as dev_mod

    with pytest.raises(SystemExit) as excinfo:
        dev_mod.main([])
    assert excinfo.value.code == 1


def test_main_checks_embedding_model_before_uvicorn(project_dir: Path, monkeypatch):
    """main() verifies the embedding model is available before starting uvicorn.

    Guards against accidentally removing the check_model_available call —
    without it, the server would start but fail at the first /search request.
    """
    monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))

    import guru_server.dev as dev_mod

    call_order: list[str] = []
    monkeypatch.setattr(dev_mod, "check_ollama_installed", lambda: None)
    monkeypatch.setattr(dev_mod, "start_ollama_serve", lambda: None)
    monkeypatch.setattr(dev_mod, "stop_ollama_serve", lambda proc: None)
    monkeypatch.setattr(
        dev_mod,
        "check_model_available",
        lambda model: call_order.append(f"model:{model}"),
    )
    monkeypatch.setattr(
        dev_mod.uvicorn,
        "run",
        lambda app_ref, **kw: call_order.append("uvicorn"),
    )

    dev_mod.main([])
    assert call_order == ["model:nomic-embed-text", "uvicorn"]
