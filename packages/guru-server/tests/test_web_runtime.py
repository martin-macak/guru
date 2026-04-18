from __future__ import annotations

from pathlib import Path

from guru_core.types import GraphConfig, GuruConfig
from guru_server.config import load_config, resolve_config, resolve_web_config
from guru_server.web_runtime import build_web_runtime


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
