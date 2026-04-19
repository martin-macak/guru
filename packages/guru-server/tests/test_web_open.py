from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from guru_core.types import GraphConfig, GuruConfig
from guru_server.app import create_app
from guru_server.web_runtime import open_web_browser


def _make_app(tmp_path) -> tuple:
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
    return app, store, embedder


def test_open_web_browser_returns_false_without_url():
    assert open_web_browser(None) is False


def test_open_web_browser_opens_when_url_present():
    with patch("webbrowser.open", return_value=True) as mock_open:
        assert open_web_browser("http://127.0.0.1:41773") is True

    mock_open.assert_called_once_with("http://127.0.0.1:41773")


def test_web_open_returns_opened_url(tmp_path):
    app, _, _ = _make_app(tmp_path)
    app.state.web_runtime = SimpleNamespace(
        enabled=True,
        available=True,
        url="http://127.0.0.1:41773",
        reason=None,
        auto_open=False,
    )

    with (
        patch("guru_server.api.web.open_web_browser", return_value=True) as mock_open,
        TestClient(app) as client,
    ):
        response = client.post("/web/open")

    assert response.status_code == 200
    assert response.json() == {"opened": True, "url": "http://127.0.0.1:41773"}
    mock_open.assert_called_once_with("http://127.0.0.1:41773")


def test_web_open_returns_unavailable_when_url_missing(tmp_path):
    app, _, _ = _make_app(tmp_path)
    app.state.web_runtime = SimpleNamespace(
        enabled=True,
        available=False,
        url=None,
        reason="assets_missing",
        auto_open=False,
    )

    with (
        patch("guru_server.api.web.open_web_browser", return_value=False) as mock_open,
        TestClient(app) as client,
    ):
        response = client.post("/web/open")

    assert response.status_code == 200
    assert response.json() == {"opened": False, "url": None}
    mock_open.assert_called_once_with(None)
