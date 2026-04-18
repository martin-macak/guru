from __future__ import annotations

from pathlib import Path

import pytest

from guru_core.types import MatchConfig, Rule
from guru_server.ingestion.markdown import MarkdownParser


@pytest.fixture
def md_tmp(tmp_path: Path) -> Path:
    p = tmp_path / "guide.md"
    p.write_text("# Title\n\n## Section A\n\ncontent A\n\n## Section B\n\ncontent B\n")
    return p


def test_markdown_parser_returns_parse_result(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha", rel_path=md_tmp.name)
    assert result.document.label == "Document"
    assert result.document.node_id == f"alpha::{md_tmp.name}"
    assert result.document.properties["language"] == "markdown"
    assert result.document.properties["file_type"] == "doc"
    assert len(result.chunks) >= 2


def test_markdown_parser_emits_section_nodes(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha", rel_path=md_tmp.name)
    section_nodes = [n for n in result.nodes if n.label == "MarkdownSection"]
    assert len(section_nodes) >= 2


def test_markdown_parser_emits_contains_edges(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha", rel_path=md_tmp.name)
    contains = [e for e in result.edges if e.rel_type == "CONTAINS"]
    assert any(e.from_id == result.document.node_id for e in contains)


def test_markdown_parser_chunks_carry_pointer_metadata(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha", rel_path=md_tmp.name)
    for c in result.chunks:
        assert c.kind == "markdown_section"
        assert c.language == "markdown"
        assert c.parent_document_id == result.document.node_id
        assert c.artifact_qualname is not None


def test_markdown_parser_name_property():
    assert MarkdownParser().name == "markdown"


def test_markdown_parser_h2_merge_keeps_nodes_aligned_with_chunks(tmp_path: Path):
    """Under split_level='h2', section_nodes must not contain phantom nodes
    for sub-sections that were merged into their parents."""
    from guru_core.types import ChunkingConfig

    p = tmp_path / "nested.md"
    p.write_text(
        "# Title\n\n"
        "## Section A\n\ncontent A\n\n"
        "### Sub A1\n\nsub A1 content\n\n"
        "### Sub A2\n\nsub A2 content\n\n"
        "## Section B\n\ncontent B\n"
    )
    parser = MarkdownParser()
    rule = Rule(
        ruleName="default",
        match=MatchConfig(glob="**/*.md"),
        chunking=ChunkingConfig(split_level="h2"),
    )
    result = parser.parse(p, rule, kb_name="alpha", rel_path=p.name)

    section_breadcrumbs = {
        sn.properties["breadcrumb"] for sn in result.nodes if sn.label == "MarkdownSection"
    }
    chunk_breadcrumbs = {c.header_breadcrumb for c in result.chunks}

    # Every section node must have a matching chunk
    assert section_breadcrumbs.issubset(chunk_breadcrumbs), (
        f"phantom nodes: {section_breadcrumbs - chunk_breadcrumbs}"
    )

    # Sub-sections should be absent from both
    assert not any("Sub A1" in b or "Sub A2" in b for b in section_breadcrumbs)
    assert not any("Sub A1" in b or "Sub A2" in b for b in chunk_breadcrumbs)
