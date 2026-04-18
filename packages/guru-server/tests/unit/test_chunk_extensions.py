from __future__ import annotations

from guru_server.ingestion.base import Chunk


def test_chunk_defaults_for_new_fields():
    c = Chunk(content="hi", file_path="x.md", header_breadcrumb="Doc", chunk_level=1)
    assert c.kind == "text"
    assert c.language is None
    assert c.artifact_qualname is None
    assert c.parent_document_id is None


def test_chunk_accepts_all_new_fields():
    c = Chunk(
        content="def foo(): pass",
        file_path="x.py",
        header_breadcrumb="x.py",
        chunk_level=1,
        kind="code",
        language="python",
        artifact_qualname="alpha::x.foo",
        parent_document_id="alpha::x.py",
    )
    assert c.kind == "code"
    assert c.language == "python"
    assert c.artifact_qualname == "alpha::x.foo"
    assert c.parent_document_id == "alpha::x.py"
