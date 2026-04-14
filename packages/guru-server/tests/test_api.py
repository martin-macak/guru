from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from guru_server.app import create_app


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.chunk_count.return_value = 100
    store.document_count.return_value = 1
    store.list_documents.return_value = [
        {
            "file_path": "specs/auth.md",
            "frontmatter": {"title": "Auth"},
            "labels": ["spec"],
            "chunk_count": 5,
        },
    ]
    store.get_document.return_value = {
        "file_path": "specs/auth.md",
        "content": "# Auth\n\nOAuth flow.",
        "frontmatter": {"title": "Auth"},
        "labels": ["spec"],
        "chunk_count": 5,
    }
    store.get_section.return_value = {
        "file_path": "specs/auth.md",
        "header_breadcrumb": "Auth > OAuth",
        "content": "OAuth 2.0 flow",
        "chunk_level": 2,
    }
    store.search.return_value = [
        {
            "content": "OAuth 2.0 flow",
            "file_path": "specs/auth.md",
            "header_breadcrumb": "Auth > OAuth",
            "chunk_level": 2,
            "labels": ["spec"],
            "score": 0.95,
        },
    ]
    return store


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 768)
    embedder.embed_batch = AsyncMock(return_value=[[0.1] * 768])
    return embedder


@pytest.fixture
def embed_cache(tmp_path):
    from guru_server.embed_cache import EmbeddingCache

    cache = EmbeddingCache(db_path=tmp_path / "test_embeddings.db")
    yield cache
    cache.close()


@pytest.fixture
def app(mock_store, mock_embedder, embed_cache):
    return create_app(
        store=mock_store,
        embedder=mock_embedder,
        embed_cache=embed_cache,
        auto_index=False,
    )


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_status(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server_running"] is True
    assert data["chunk_count"] == 100
    assert data["document_count"] == 1
    assert data["last_indexed"] is None
    assert data["ollama_available"] is True
    assert data["model_loaded"] is True
    assert data["current_job"] is None


def test_get_status_with_running_job(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
    job = app.state.job_registry.create_job()
    job.status = "running"
    job.phase = "indexing"
    job.files_total = 10
    job.files_processed = 5
    job.files_skipped = 2
    with TestClient(app) as c:
        data = c.get("/status").json()
        assert data["current_job"] is not None
        assert data["current_job"]["job_id"] == job.job_id
        assert data["current_job"]["status"] == "running"
        assert data["current_job"]["files_total"] == 10


def test_post_index_returns_accepted(client):
    resp = client.post("/index", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] in ("queued", "running")
    assert "message" in data


def test_post_index_returns_existing_job(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
    job = app.state.job_registry.create_job()
    job.status = "running"
    with TestClient(app) as c:
        resp = c.post("/index", json={})
        data = resp.json()
        assert data["job_id"] == job.job_id
        assert data["message"] == "Indexing already in progress"


def test_get_job_detail(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
    job = app.state.job_registry.create_job()
    job.status = "completed"
    job.files_total = 5
    job.files_processed = 5
    with TestClient(app) as c:
        resp = c.get(f"/jobs/{job.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job.job_id
        assert data["status"] == "completed"


def test_get_job_not_found(client):
    resp = client.get("/jobs/nonexistent")
    assert resp.status_code == 404


def test_list_documents(client):
    resp = client.get("/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file_path"] == "specs/auth.md"


def test_list_documents_with_label_filter(client, mock_store):
    mock_store.list_documents.return_value = [
        {
            "file_path": "specs/auth.md",
            "frontmatter": {"title": "Auth"},
            "labels": ["spec"],
            "chunk_count": 5,
        },
        {
            "file_path": "specs/rbac.md",
            "frontmatter": {"title": "RBAC"},
            "labels": ["spec", "security"],
            "chunk_count": 3,
        },
    ]
    resp = client.get("/documents?labels=security")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file_path"] == "specs/rbac.md"


def test_list_documents_with_unsupported_filter(client):
    resp = client.get("/documents?unknown_col=foo")
    assert resp.status_code == 400


def test_get_document(client):
    resp = client.get("/documents/specs/auth.md")
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_path"] == "specs/auth.md"
    assert "content" in data


def test_get_document_not_found(client, mock_store):
    mock_store.get_document.return_value = None
    resp = client.get("/documents/nonexistent.md")
    assert resp.status_code == 404


def test_get_section(client):
    resp = client.get("/documents/specs/auth.md/sections/Auth > OAuth")
    assert resp.status_code == 200
    data = resp.json()
    assert data["header_breadcrumb"] == "Auth > OAuth"


def test_get_section_not_found(client, mock_store):
    mock_store.get_section.return_value = None
    resp = client.get("/documents/specs/auth.md/sections/Nonexistent")
    assert resp.status_code == 404


def test_search(client):
    resp = client.post("/search", json={"query": "authentication"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file_path"] == "specs/auth.md"


def test_search_with_filters(client):
    resp = client.post(
        "/search", json={"query": "auth", "n_results": 5, "filters": {"labels": "spec"}}
    )
    assert resp.status_code == 200


def test_search_with_disallowed_filter(client):
    resp = client.post("/search", json={"query": "auth", "filters": {"arbitrary_col": "value"}})
    assert resp.status_code == 400


def test_get_cache_stats_empty(client):
    resp = client.get("/cache")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 0
    assert data["by_model"] == {}


def test_delete_cache_clears_all(client, app):
    import hashlib

    import numpy as np

    key = (hashlib.sha256(b"hello").digest(), "nomic-embed-text")
    app.state.embed_cache.put_many([(key, np.array([0.1] * 768, dtype=np.float32))])

    resp = client.delete("/cache")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert app.state.embed_cache.stats().total_entries == 0


def test_delete_cache_scoped_by_model(client, app):
    import hashlib

    import numpy as np

    app.state.embed_cache.put_many(
        [
            ((hashlib.sha256(b"a").digest(), "m1"), np.array([1.0], dtype=np.float32)),
            ((hashlib.sha256(b"b").digest(), "m2"), np.array([2.0], dtype=np.float32)),
        ]
    )

    resp = client.delete("/cache?model=m1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert app.state.embed_cache.stats().total_entries == 1


def test_prune_cache(client, app):
    import hashlib

    import numpy as np

    key = (hashlib.sha256(b"old").digest(), "m1")
    app.state.embed_cache.put_many([(key, np.array([1.0], dtype=np.float32))])
    old_ts_ms = 0
    app.state.embed_cache._conn.execute(
        "UPDATE embeddings SET accessed_at = ? WHERE content_hash = ?",
        (old_ts_ms, key[0]),
    )

    resp = client.post("/cache/prune", json={"older_than_ms": 1000})
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1


def test_status_includes_cache_section(client, app):
    import hashlib

    import numpy as np

    key = (hashlib.sha256(b"hello").digest(), "nomic-embed-text")
    app.state.embed_cache.put_many([(key, np.array([0.1] * 768, dtype=np.float32))])

    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "cache" in data
    assert data["cache"] is not None
    assert data["cache"]["total_entries"] == 1


def test_status_includes_last_job_hit_rate(client, app):
    """When a completed job exists, /status reports its cache counters
    and computed hit rate via _assemble_stats.
    """
    from datetime import UTC, datetime

    job = app.state.job_registry.create_job()
    job.status = "completed"
    job.cache_hits = 7
    job.cache_misses = 3
    job.finished_at = datetime.now(UTC)

    resp = client.get("/status")
    assert resp.status_code == 200
    cache_data = resp.json()["cache"]
    assert cache_data["last_job_hits"] == 7
    assert cache_data["last_job_misses"] == 3
    assert cache_data["last_job_hit_rate"] == pytest.approx(0.7)


def test_status_last_job_hit_rate_is_none_when_no_chunks(client, app):
    """A completed job with zero chunks (hits + misses == 0) yields a
    null hit rate, not a division-by-zero.
    """
    from datetime import UTC, datetime

    job = app.state.job_registry.create_job()
    job.status = "completed"
    job.cache_hits = 0
    job.cache_misses = 0
    job.finished_at = datetime.now(UTC)

    resp = client.get("/status")
    assert resp.status_code == 200
    cache_data = resp.json()["cache"]
    assert cache_data["last_job_hits"] == 0
    assert cache_data["last_job_misses"] == 0
    assert cache_data["last_job_hit_rate"] is None


def test_prune_cache_rejects_negative_older_than(client):
    """CachePruneRequest has older_than_ms: int = Field(ge=0).
    FastAPI must reject a negative value at the HTTP boundary with 422.
    """
    resp = client.post("/cache/prune", json={"older_than_ms": -1})
    assert resp.status_code == 422
