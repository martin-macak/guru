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
def client(mock_store, mock_embedder):
    app = create_app(store=mock_store, embedder=mock_embedder, auto_index=False)
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
