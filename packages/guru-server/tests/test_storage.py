import pytest
from guru_server.storage import VectorStore
from guru_server.ingestion.base import Chunk

@pytest.fixture
def store(tmp_path):
    return VectorStore(db_path=str(tmp_path / "db"))

@pytest.fixture
def sample_chunks():
    return [
        Chunk(content="OAuth 2.0 authentication flow", file_path="specs/auth.md",
              header_breadcrumb="Auth > OAuth", chunk_level=2,
              frontmatter={"title": "Auth Spec", "status": "approved"},
              labels=["spec"], chunk_id="abc123"),
        Chunk(content="Token refresh happens every 30 minutes", file_path="specs/auth.md",
              header_breadcrumb="Auth > OAuth > Token Refresh", chunk_level=3,
              frontmatter={"title": "Auth Spec", "status": "approved"},
              labels=["spec"], chunk_id="def456"),
        Chunk(content="Role-based access control for API endpoints", file_path="specs/rbac.md",
              header_breadcrumb="RBAC > API Access", chunk_level=2,
              frontmatter={"title": "RBAC Spec", "status": "draft"},
              labels=["spec", "security"], chunk_id="ghi789"),
    ]

def test_add_and_count(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    assert store.chunk_count() == 3

def test_search_returns_results(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    results = store.search(query_vector=[0.1] * 768, n_results=2)
    assert len(results) == 2
    assert all("file_path" in r for r in results)

def test_search_with_label_filter(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    results = store.search(query_vector=[0.1] * 768, n_results=10, where="labels LIKE '%security%'")
    assert len(results) >= 1
    assert all("security" in r.get("labels", "") for r in results)

def test_list_documents(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    docs = store.list_documents()
    file_paths = [d["file_path"] for d in docs]
    assert "specs/auth.md" in file_paths
    assert "specs/rbac.md" in file_paths

def test_get_document(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    doc = store.get_document("specs/auth.md")
    assert doc is not None
    assert doc["file_path"] == "specs/auth.md"
    assert doc["chunk_count"] == 2

def test_get_document_not_found(store):
    doc = store.get_document("nonexistent.md")
    assert doc is None

def test_get_section(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    section = store.get_section("specs/auth.md", "Auth > OAuth > Token Refresh")
    assert section is not None
    assert "Token refresh" in section["content"]
