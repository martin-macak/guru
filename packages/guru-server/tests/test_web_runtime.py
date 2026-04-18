from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

import httpx
import uvicorn

from guru_core.types import GraphConfig, GuruConfig
from guru_server.app import create_app
from guru_server.config import load_config, resolve_config, resolve_web_config
from guru_server.web_runtime import bind_web_listener_sockets, build_web_runtime


def test_resolve_web_config_defaults_when_config_has_no_web():
    cfg = resolve_web_config(GuruConfig(graph=GraphConfig(enabled=False)))
    assert cfg.enabled is True
    assert cfg.auto_open is False


def test_load_config_parses_web_settings(tmp_path: Path):
    config_file = tmp_path / ".guru.json"
    config_file.write_text(
        '{"version": 1, "rules": [], "web": {"enabled": false, "autoOpen": true}}'
    )

    cfg = load_config(config_file)
    assert cfg is not None
    assert cfg.web.enabled is False
    assert cfg.web.auto_open is True


def test_resolve_config_preserves_global_web_settings_when_local_omits_web(tmp_path: Path):
    global_dir = tmp_path / "global"
    project_dir = tmp_path / "project"
    global_dir.mkdir()
    project_dir.mkdir()
    (global_dir / "config.json").write_text(
        '{"version": 1, "rules": [], "web": {"enabled": false, "autoOpen": true}}'
    )
    (project_dir / ".guru.json").write_text('{"version": 1, "rules": []}')

    cfg = resolve_config(project_root=project_dir, global_config_dir=global_dir)
    assert cfg.web.enabled is False
    assert cfg.web.auto_open is True


def test_resolve_config_local_web_overrides_global_web(tmp_path: Path):
    global_dir = tmp_path / "global"
    project_dir = tmp_path / "project"
    global_dir.mkdir()
    project_dir.mkdir()
    (global_dir / "config.json").write_text(
        '{"version": 1, "rules": [], "web": {"enabled": false, "autoOpen": true}}'
    )
    (project_dir / ".guru.json").write_text(
        '{"version": 1, "rules": [], "web": {"enabled": true, "autoOpen": false}}'
    )

    cfg = resolve_config(project_root=project_dir, global_config_dir=global_dir)
    assert cfg.web.enabled is True
    assert cfg.web.auto_open is False


def test_missing_assets_yields_unavailable_runtime(tmp_path: Path):
    runtime = build_web_runtime(
        project_root=tmp_path,
        assets_dir=tmp_path / "missing-dist",
        enabled=True,
    )
    assert runtime.enabled is True
    assert runtime.available is False
    assert runtime.url is None
    assert runtime.port is None
    assert runtime.assets_dir is None
    assert runtime.reason == "assets_missing"


def test_existing_assets_allocate_localhost_port(tmp_path: Path):
    assets_dir = tmp_path / "packages" / "guru-web" / "dist"
    assets_dir.mkdir(parents=True)
    (assets_dir / "index.html").write_text("<html><body>Guru Web</body></html>")

    runtime = build_web_runtime(
        project_root=tmp_path,
        assets_dir=assets_dir,
        enabled=True,
        auto_open=True,
    )

    assert runtime.enabled is True
    assert runtime.available is True
    assert runtime.url is not None
    assert runtime.url.startswith("http://127.0.0.1:")
    assert runtime.port is not None
    assert runtime.assets_dir == assets_dir
    assert runtime.reason is None
    assert runtime.auto_open is True


def test_web_runtime_listener_serves_frontend_and_boot(tmp_path: Path):
    assets_dir = tmp_path / "packages" / "guru-web" / "dist"
    assets_dir.mkdir(parents=True)
    (assets_dir / "index.html").write_text("<html><body>Guru Web</body></html>")

    store = type("Store", (), {"chunk_count": lambda self: 0, "document_count": lambda self: 0})()
    embedder = type("Embedder", (), {"check_health": lambda self: None})()
    app = create_app(
        store=store,
        embedder=embedder,
        config=GuruConfig(graph=GraphConfig(enabled=False)),
        project_root=str(tmp_path),
        auto_index=False,
    )

    runtime = app.state.web_runtime
    assert runtime.available is True
    assert runtime.port is not None
    assert runtime.url is not None

    uds_path = Path("/tmp") / f"guru-web-{os.getpid()}-{uuid.uuid4().hex}.sock"
    sockets = bind_web_listener_sockets(uds_path=uds_path, port=runtime.port)
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": sockets}, daemon=True)
    thread.start()

    try:
        deadline = time.monotonic() + 5
        response = None
        while time.monotonic() < deadline:
            try:
                response = httpx.get(runtime.url, timeout=0.5)
                if response.status_code == 200:
                    break
            except Exception:
                time.sleep(0.05)
        assert response is not None
        assert response.status_code == 200
        assert "Guru Web" in response.text

        boot = httpx.get(f"{runtime.url}/web/boot", timeout=1.0)
        assert boot.status_code == 200
        boot_data = boot.json()
        assert boot_data["web"]["available"] is True
        assert boot_data["web"]["url"] == runtime.url
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        for sock in sockets:
            sock.close()
        uds_path.unlink(missing_ok=True)

    assert not thread.is_alive()
