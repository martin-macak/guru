from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from guru_core.types import GraphConfig, GuruConfig
from guru_server.app import create_app


def _make_app(tmp_path, *, assets: bool) -> tuple:
    assets_dir = None
    if assets:
        assets_dir = tmp_path / "packages" / "guru-web" / "dist"
        assets_dir.mkdir(parents=True)
        (assets_dir / "index.html").write_text("<html><body>Guru Web</body></html>")

    store = MagicMock()
    store.chunk_count.return_value = 0
    store.document_count.return_value = 0
    embedder = MagicMock()
    embedder.check_health = AsyncMock()

    app = create_app(
        store=store,
        embedder=embedder,
        config=GuruConfig(graph=GraphConfig(enabled=False)),
        project_root=str(tmp_path),
        auto_index=False,
    )
    return app, assets_dir


def test_web_boot_reports_unavailable_runtime(tmp_path):
    app, _ = _make_app(tmp_path, assets=False)
    app.state.web_runtime = SimpleNamespace(
        enabled=True,
        available=False,
        url=None,
        reason="assets_missing",
        auto_open=False,
    )

    with TestClient(app) as client:
        response = client.get("/web/boot")
        status = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["project"]["root"] == str(tmp_path)
    assert data["web"]["enabled"] is True
    assert data["web"]["available"] is False
    assert data["web"]["url"] is None
    assert data["web"]["reason"] == "assets_missing"
    assert data["web"]["autoOpen"] is False
    assert data["graph"]["enabled"] is False

    assert status.status_code == 200
    status_data = status.json()
    assert status_data["web"]["enabled"] is True
    assert status_data["web"]["available"] is False
    assert status_data["web"]["reason"] == "assets_missing"


def test_web_boot_reports_available_runtime(tmp_path):
    app, _ = _make_app(tmp_path, assets=True)
    app.state.web_runtime = SimpleNamespace(
        enabled=True,
        available=True,
        url="http://127.0.0.1:41773",
        reason=None,
        auto_open=True,
    )

    with TestClient(app) as client:
        response = client.get("/web/boot")
        status = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["project"]["name"] == app.state.project_name
    assert data["web"]["enabled"] is True
    assert data["web"]["available"] is True
    assert data["web"]["url"] == "http://127.0.0.1:41773"
    assert data["web"]["reason"] is None
    assert data["web"]["autoOpen"] is True
    assert data["graph"]["enabled"] is False

    assert status.status_code == 200
    status_data = status.json()
    assert status_data["web"]["available"] is True
    assert status_data["web"]["url"] == "http://127.0.0.1:41773"
