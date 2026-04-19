from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from guru_core.graph_errors import GraphUnavailable
from guru_server.app import create_app


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.chunk_count.return_value = 0
    store.document_count.return_value = 0
    return store


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.check_health = AsyncMock()
    return embedder


@pytest.fixture
def embed_cache(tmp_path):
    from guru_server.embed_cache import EmbeddingCache

    cache = EmbeddingCache(db_path=tmp_path / "test_embeddings.db")
    yield cache
    cache.close()


@pytest.fixture
def app_with_graph(mock_store, mock_embedder, embed_cache):
    app = create_app(
        store=mock_store,
        embedder=mock_embedder,
        embed_cache=embed_cache,
        auto_index=False,
    )
    app.state.graph_client = MagicMock()
    app.state.graph_enabled = True
    return app


def test_graph_describe_proxies_to_graph_client(app_with_graph):
    app_with_graph.state.graph_client.describe_artifact = AsyncMock(
        return_value=MagicMock(
            model_dump=MagicMock(
                return_value={
                    "id": "alpha::pkg.Widget",
                    "label": "Class",
                    "properties": {"name": "Widget"},
                }
            )
        )
    )
    with TestClient(app_with_graph) as client:
        response = client.get("/graph/describe/alpha::pkg.Widget")
    assert response.status_code == 200
    app_with_graph.state.graph_client.describe_artifact.assert_awaited_once_with(
        "alpha::pkg.Widget"
    )


def test_graph_describe_returns_stable_sentinel_when_graph_disabled(
    mock_store, mock_embedder, embed_cache
):
    app = create_app(
        store=mock_store,
        embedder=mock_embedder,
        embed_cache=embed_cache,
        auto_index=False,
    )
    app.state.graph_client = None
    app.state.graph_enabled = False
    with TestClient(app) as client:
        response = client.get("/graph/describe/alpha::pkg.Widget")
    assert response.status_code == 200
    assert response.json() == {"status": "graph_disabled"}


def test_graph_neighbors_proxies_query_params(app_with_graph):
    app_with_graph.state.graph_client.neighbors = AsyncMock(
        return_value=MagicMock(
            model_dump=MagicMock(
                return_value={
                    "node_id": "alpha::pkg.Widget",
                    "nodes": [],
                    "edges": [],
                }
            )
        )
    )
    with TestClient(app_with_graph) as client:
        response = client.get(
            "/graph/neighbors/alpha::pkg.Widget"
            "?direction=out&rel_type=RELATES&kind=references&depth=2&limit=10"
        )
    assert response.status_code == 200
    app_with_graph.state.graph_client.neighbors.assert_awaited_once_with(
        "alpha::pkg.Widget",
        direction="out",
        rel_type="RELATES",
        kind="references",
        depth=2,
        limit=10,
    )


def test_graph_find_posts_body_to_graph_client(app_with_graph):
    app_with_graph.state.graph_client.find_artifacts = AsyncMock(
        return_value=[
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "id": "alpha::pkg.Widget",
                        "label": "Class",
                        "properties": {"name": "Widget"},
                    }
                )
            )
        ]
    )
    with TestClient(app_with_graph) as client:
        response = client.post(
            "/graph/find",
            json={"name": "Widget", "label": "Class", "kb_name": "alpha", "limit": 5},
        )
    assert response.status_code == 200
    app_with_graph.state.graph_client.find_artifacts.assert_awaited_once()
    query = app_with_graph.state.graph_client.find_artifacts.await_args.args[0]
    assert query.name == "Widget"
    assert query.label == "Class"
    assert query.kb_name == "alpha"
    assert query.limit == 5


def test_graph_proxy_returns_stable_sentinel_on_graph_unavailable(app_with_graph):
    app_with_graph.state.graph_client.find_artifacts = AsyncMock(
        side_effect=GraphUnavailable("daemon unreachable")
    )
    with TestClient(app_with_graph) as client:
        response = client.post("/graph/find", json={"name": "Widget"})
    assert response.status_code == 200
    assert response.json() == {"status": "graph_disabled"}
