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
              labels=["spec"], chunk_id="abc123", content_type="text"),
        Chunk(content="Token refresh happens every 30 minutes", file_path="specs/auth.md",
              header_breadcrumb="Auth > OAuth > Token Refresh", chunk_level=3,
              frontmatter={"title": "Auth Spec", "status": "approved"},
              labels=["spec"], chunk_id="def456", content_type="text"),
        Chunk(content="Role-based access control for API endpoints", file_path="specs/rbac.md",
              header_breadcrumb="RBAC > API Access", chunk_level=2,
              frontmatter={"title": "RBAC Spec", "status": "draft"},
              labels=["spec", "security"], chunk_id="ghi789", content_type="text"),
    ]

def test_add_and_count(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    assert store.chunk_count() == 3

def test_add_chunks_length_mismatch(store, sample_chunks):
    with pytest.raises(ValueError, match="same length"):
        store.add_chunks(sample_chunks, [[0.1] * 768])

def test_add_chunks_wrong_vector_dim(store, sample_chunks):
    with pytest.raises(ValueError, match="dimension"):
        store.add_chunks(sample_chunks[:1], [[0.1] * 100])

def test_document_count(store, sample_chunks):
    assert store.document_count() == 0
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    assert store.document_count() == 2

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
    assert all("security" in r.get("labels", []) for r in results)

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

def test_get_document_stable_order(store, sample_chunks):
    """Re-indexing should return chunks in ingestion order."""
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    doc1 = store.get_document("specs/auth.md")
    # Index again (delete + re-add)
    store.delete_files(["specs/auth.md"])
    store.add_chunks(sample_chunks[:2], fake_vectors[:2])
    doc2 = store.get_document("specs/auth.md")
    assert doc1["content"] == doc2["content"]

def test_get_document_not_found(store):
    doc = store.get_document("nonexistent.md")
    assert doc is None

def test_get_section(store, sample_chunks):
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    section = store.get_section("specs/auth.md", "Auth > OAuth > Token Refresh")
    assert section is not None
    assert "Token refresh" in section["content"]

def test_delete_files_prevents_duplicates(store, sample_chunks):
    """Re-indexing should not duplicate chunks."""
    fake_vectors = [[0.1] * 768 for _ in sample_chunks]
    store.add_chunks(sample_chunks, fake_vectors)
    assert store.chunk_count() == 3

    # Re-index auth.md
    store.delete_files(["specs/auth.md"])
    store.add_chunks(sample_chunks[:2], fake_vectors[:2])
    # Still 3 total chunks (2 auth + 1 rbac)
    assert store.chunk_count() == 3
