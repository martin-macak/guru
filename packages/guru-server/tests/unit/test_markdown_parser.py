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
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    assert result.document.label == "Document"
    assert result.document.node_id.startswith("alpha::")
    assert result.document.properties["language"] == "markdown"
    assert result.document.properties["file_type"] == "doc"
    assert len(result.chunks) >= 2


def test_markdown_parser_emits_section_nodes(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    section_nodes = [n for n in result.nodes if n.label == "MarkdownSection"]
    assert len(section_nodes) >= 2


def test_markdown_parser_emits_contains_edges(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    contains = [e for e in result.edges if e.rel_type == "CONTAINS"]
    assert any(e.from_id == result.document.node_id for e in contains)


def test_markdown_parser_chunks_carry_pointer_metadata(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    for c in result.chunks:
        assert c.kind == "markdown_section"
        assert c.language == "markdown"
        assert c.parent_document_id == result.document.node_id
        assert c.artifact_qualname is not None


def test_markdown_parser_name_property():
    assert MarkdownParser().name == "markdown"
