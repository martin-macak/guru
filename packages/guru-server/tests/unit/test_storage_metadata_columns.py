from __future__ import annotations

from pathlib import Path

from guru_server.ingestion.base import Chunk
from guru_server.storage import VectorStore


def test_add_chunks_persists_metadata_columns(tmp_path: Path):
    store = VectorStore(db_path=str(tmp_path / "db"))
    chunk = Chunk(
        content="def foo(): pass",
        file_path="x.py",
        header_breadcrumb="x.py",
        chunk_level=1,
        kind="code",
        language="python",
        artifact_qualname="kb::x.foo",
        parent_document_id="kb::x.py",
        chunk_id="abc",
    )
    store.add_chunks([chunk], [[0.0] * 768])
    table = store._get_table()
    rows = table.search(None).to_list()
    assert rows[0]["kind"] == "code"
    assert rows[0]["language"] == "python"
    assert rows[0]["artifact_qualname"] == "kb::x.foo"
    assert rows[0]["parent_document_id"] == "kb::x.py"
