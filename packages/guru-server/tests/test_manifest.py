import pytest

from guru_server.manifest import FileManifest


@pytest.fixture
def manifest(tmp_path):
    import lancedb

    db = lancedb.connect(str(tmp_path / "db"))
    return FileManifest(db)


def test_get_entry_returns_none_for_unknown(manifest):
    assert manifest.get_entry("nonexistent.md") is None


def test_upsert_and_get_entry(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc123", mtime=1000.0, chunk_count=5)
    entry = manifest.get_entry("docs/guide.md")
    assert entry is not None
    assert entry["file_path"] == "docs/guide.md"
    assert entry["content_hash"] == "abc123"
    assert entry["mtime"] == 1000.0
    assert entry["chunk_count"] == 5
    assert entry["indexed_at"] > 0


def test_upsert_overwrites_existing(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1000.0, chunk_count=3)
    manifest.upsert("docs/guide.md", content_hash="def", mtime=2000.0, chunk_count=5)
    entry = manifest.get_entry("docs/guide.md")
    assert entry["content_hash"] == "def"
    assert entry["mtime"] == 2000.0
    assert entry["chunk_count"] == 5


def test_all_entries(manifest):
    manifest.upsert("a.md", content_hash="aaa", mtime=1.0, chunk_count=1)
    manifest.upsert("b.md", content_hash="bbb", mtime=2.0, chunk_count=2)
    entries = manifest.all_entries()
    paths = {e["file_path"] for e in entries}
    assert paths == {"a.md", "b.md"}


def test_delete_entry(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1.0, chunk_count=3)
    manifest.delete_entry("docs/guide.md")
    assert manifest.get_entry("docs/guide.md") is None


def test_delete_entries_batch(manifest):
    manifest.upsert("a.md", content_hash="aaa", mtime=1.0, chunk_count=1)
    manifest.upsert("b.md", content_hash="bbb", mtime=2.0, chunk_count=2)
    manifest.upsert("c.md", content_hash="ccc", mtime=3.0, chunk_count=3)
    manifest.delete_entries(["a.md", "b.md"])
    assert manifest.get_entry("a.md") is None
    assert manifest.get_entry("b.md") is None
    assert manifest.get_entry("c.md") is not None


def test_update_mtime_only(manifest):
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1000.0, chunk_count=3)
    manifest.update_mtime("docs/guide.md", mtime=2000.0)
    entry = manifest.get_entry("docs/guide.md")
    assert entry["mtime"] == 2000.0
    assert entry["content_hash"] == "abc"  # unchanged
