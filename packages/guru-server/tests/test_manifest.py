import glob
import os

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


def _corrupt_lance_table(db_path, table_name):
    """Delete data files from a LanceDB table to simulate corruption."""
    data_dir = os.path.join(db_path, f"{table_name}.lance", "data")
    for f in glob.glob(os.path.join(data_dir, "*.lance")):
        os.remove(f)


def test_corrupted_manifest_is_detected_and_dropped(tmp_path):
    """A corrupted manifest table auto-recovers on first access."""
    import lancedb

    db_path = str(tmp_path / "db")
    db = lancedb.connect(db_path)
    manifest = FileManifest(db)
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1.0, chunk_count=3)
    assert manifest.get_entry("docs/guide.md") is not None

    # Simulate corruption: remove data files, create fresh manifest
    _corrupt_lance_table(db_path, "file_manifest")
    db2 = lancedb.connect(db_path)
    manifest2 = FileManifest(db2)

    # Table should be detected as corrupted, dropped, and return empty
    assert manifest2.get_entry("docs/guide.md") is None
    assert manifest2.all_entries() == []

    # Should be able to add new data after recovery
    manifest2.upsert("docs/new.md", content_hash="xyz", mtime=2.0, chunk_count=1)
    assert manifest2.get_entry("docs/new.md") is not None


def test_healthy_manifest_is_not_dropped(tmp_path):
    """A valid manifest table is not affected by the corruption check."""
    import lancedb

    db_path = str(tmp_path / "db")
    db = lancedb.connect(db_path)
    manifest = FileManifest(db)
    manifest.upsert("docs/guide.md", content_hash="abc", mtime=1.0, chunk_count=3)

    # Fresh manifest instance should find existing data
    db2 = lancedb.connect(db_path)
    manifest2 = FileManifest(db2)
    assert manifest2.get_entry("docs/guide.md") is not None


def test_reset_clears_manifest(tmp_path):
    """FileManifest.reset() drops the table for a clean slate."""
    import lancedb

    db_path = str(tmp_path / "db")
    db = lancedb.connect(db_path)
    manifest = FileManifest(db)
    manifest.upsert("a.md", content_hash="aaa", mtime=1.0, chunk_count=1)
    manifest.upsert("b.md", content_hash="bbb", mtime=2.0, chunk_count=2)
    assert len(manifest.all_entries()) == 2

    manifest.reset()
    assert manifest.all_entries() == []

    # Can add entries after reset
    manifest.upsert("c.md", content_hash="ccc", mtime=3.0, chunk_count=3)
    assert manifest.get_entry("c.md") is not None
