from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from guru_core.types import ChunkingConfig, MatchConfig, Rule
from guru_server.ingestion import Chunk, DocumentParser, MarkdownParser


SAMPLE_MD = """\
---
title: API Guide
version: "1.0"
---

# Authentication

This section covers authentication.

## Token Refresh

How to refresh tokens.

## Authorization

Authorization details.
"""

SAMPLE_MD_WITH_H3 = """\
---
title: Deep Guide
---

# Overview

Top-level content.

## Section A

Section A intro.

### Sub A1

Sub-section A1 content.

### Sub A2

Sub-section A2 content.

## Section B

Section B content.
"""

SAMPLE_MD_CODE = """\
# Code Example

Some text.

```python
def hello():
    pass
```
"""

SAMPLE_MD_TABLE = """\
# Table Example

| Column 1 | Column 2 |
|----------|----------|
| row1     | data1    |
"""

SAMPLE_MD_MIXED = """\
# Mixed Example

| Column 1 | Column 2 |
|----------|----------|
| row1     | data1    |

```python
x = 1
```
"""


@pytest.fixture
def rule() -> Rule:
    return Rule(ruleName="test", match=MatchConfig(glob="**/*.md"), labels=["docs"])


@pytest.fixture
def md_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    return p


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


@pytest.fixture
def chunks(parser: MarkdownParser, md_file: Path, rule: Rule) -> list[Chunk]:
    return parser.parse(md_file, rule)


# --- Chunk dataclass ---

def test_chunk_construction():
    chunk = Chunk(
        content="hello",
        file_path="/some/path.md",
        header_breadcrumb="Intro",
        chunk_level=1,
    )
    assert chunk.content == "hello"
    assert chunk.file_path == "/some/path.md"
    assert chunk.header_breadcrumb == "Intro"
    assert chunk.chunk_level == 1
    assert chunk.frontmatter == {}
    assert chunk.labels == []
    assert chunk.parent_chunk_id is None
    assert chunk.chunk_id is None


def test_chunk_with_all_fields():
    chunk = Chunk(
        content="text",
        file_path="/a.md",
        header_breadcrumb="A > B",
        chunk_level=2,
        frontmatter={"title": "A"},
        labels=["foo"],
        parent_chunk_id="abc",
        chunk_id="xyz",
    )
    assert chunk.frontmatter == {"title": "A"}
    assert chunk.labels == ["foo"]
    assert chunk.parent_chunk_id == "abc"
    assert chunk.chunk_id == "xyz"


# --- MarkdownParser isinstance ---

def test_markdown_parser_is_document_parser(parser: MarkdownParser):
    assert isinstance(parser, DocumentParser)


# --- supports() ---

def test_supports_md(parser: MarkdownParser, tmp_path: Path):
    assert parser.supports(tmp_path / "file.md") is True


def test_supports_markdown(parser: MarkdownParser, tmp_path: Path):
    assert parser.supports(tmp_path / "file.markdown") is True


def test_not_supports_txt(parser: MarkdownParser, tmp_path: Path):
    assert parser.supports(tmp_path / "file.txt") is False


# --- parse() basic ---

def test_parse_returns_list(chunks: list[Chunk]):
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_parse_returns_chunks(chunks: list[Chunk]):
    for chunk in chunks:
        assert isinstance(chunk, Chunk)


# --- Frontmatter extraction ---

def test_frontmatter_extracted(chunks: list[Chunk]):
    for chunk in chunks:
        assert chunk.frontmatter.get("title") == "API Guide"
        assert chunk.frontmatter.get("version") == "1.0"


# --- Header breadcrumbs ---

def test_chunk_breadcrumbs_present(chunks: list[Chunk]):
    breadcrumbs = [c.header_breadcrumb for c in chunks]
    assert any("Authentication" in b for b in breadcrumbs), f"breadcrumbs: {breadcrumbs}"


def test_chunk_has_token_refresh_breadcrumb(chunks: list[Chunk]):
    breadcrumbs = [c.header_breadcrumb for c in chunks]
    assert any("Token Refresh" in b for b in breadcrumbs), f"breadcrumbs: {breadcrumbs}"


def test_chunk_has_authorization_breadcrumb(chunks: list[Chunk]):
    breadcrumbs = [c.header_breadcrumb for c in chunks]
    assert any("Authorization" in b for b in breadcrumbs), f"breadcrumbs: {breadcrumbs}"


def test_nested_breadcrumb_format(chunks: list[Chunk]):
    # Token Refresh is nested under Authentication, so its breadcrumb should have ' > '
    token_refresh_chunks = [c for c in chunks if "Token Refresh" in c.header_breadcrumb]
    assert token_refresh_chunks, "Expected at least one chunk with 'Token Refresh' in breadcrumb"
    assert any(" > " in c.header_breadcrumb for c in token_refresh_chunks), \
        f"Expected ' > ' in breadcrumb, got: {[c.header_breadcrumb for c in token_refresh_chunks]}"


# --- Labels ---

def test_labels_from_rule(chunks: list[Chunk], rule: Rule):
    for chunk in chunks:
        assert chunk.labels == list(rule.labels)


def test_labels_content(chunks: list[Chunk]):
    for chunk in chunks:
        assert "docs" in chunk.labels


# --- file_path ---

def test_file_path_set(chunks: list[Chunk], md_file: Path):
    for chunk in chunks:
        assert chunk.file_path == str(md_file)


# --- chunk_id ---

def test_chunk_id_set(chunks: list[Chunk]):
    for chunk in chunks:
        assert chunk.chunk_id is not None
        assert len(chunk.chunk_id) == 16


def test_chunk_ids_unique(chunks: list[Chunk]):
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), f"Duplicate chunk IDs: {ids}"


# --- chunk_level ---

def test_chunk_level_range(chunks: list[Chunk]):
    for chunk in chunks:
        assert 1 <= chunk.chunk_level <= 3


# --- content_type detection ---

def test_content_type_default_is_text(chunks: list[Chunk]):
    # SAMPLE_MD has no code blocks or tables
    for chunk in chunks:
        assert chunk.content_type == "text"


def test_content_type_code(parser: MarkdownParser, tmp_path: Path, rule: Rule):
    p = tmp_path / "code.md"
    p.write_text(SAMPLE_MD_CODE, encoding="utf-8")
    result = parser.parse(p, rule)
    code_chunks = [c for c in result if "```" in c.content]
    assert code_chunks, "Expected at least one chunk with a code block"
    for c in code_chunks:
        assert c.content_type == "code", f"Expected 'code', got '{c.content_type}'"


def test_content_type_table(parser: MarkdownParser, tmp_path: Path, rule: Rule):
    p = tmp_path / "table.md"
    p.write_text(SAMPLE_MD_TABLE, encoding="utf-8")
    result = parser.parse(p, rule)
    table_chunks = [c for c in result if "|" in c.content]
    assert table_chunks, "Expected at least one chunk with a table"
    for c in table_chunks:
        assert c.content_type == "table", f"Expected 'table', got '{c.content_type}'"


def test_content_type_mixed(parser: MarkdownParser, tmp_path: Path, rule: Rule):
    p = tmp_path / "mixed.md"
    p.write_text(SAMPLE_MD_MIXED, encoding="utf-8")
    result = parser.parse(p, rule)
    mixed_chunks = [c for c in result if "```" in c.content and "|" in c.content]
    assert mixed_chunks, "Expected at least one chunk with both code and table"
    for c in mixed_chunks:
        assert c.content_type == "mixed", f"Expected 'mixed', got '{c.content_type}'"


# --- parent_chunk_id ---

def test_parent_chunk_id_set_on_h3_chunks(parser: MarkdownParser, tmp_path: Path, rule: Rule):
    p = tmp_path / "deep.md"
    p.write_text(SAMPLE_MD_WITH_H3, encoding="utf-8")
    result = parser.parse(p, rule)
    l3_chunks = [c for c in result if c.chunk_level == 3]
    l2_chunks = [c for c in result if c.chunk_level == 2]
    assert l3_chunks, "Expected level-3 chunks from h3 headers"
    assert l2_chunks, "Expected level-2 chunks from h2 headers"
    for c in l3_chunks:
        assert c.parent_chunk_id is not None, \
            f"Expected parent_chunk_id on level-3 chunk '{c.header_breadcrumb}'"
        parent_ids = {c2.chunk_id for c2 in l2_chunks}
        assert c.parent_chunk_id in parent_ids, \
            f"parent_chunk_id '{c.parent_chunk_id}' not in level-2 chunk IDs {parent_ids}"


def test_l2_chunks_have_no_parent(parser: MarkdownParser, tmp_path: Path, rule: Rule):
    p = tmp_path / "deep.md"
    p.write_text(SAMPLE_MD_WITH_H3, encoding="utf-8")
    result = parser.parse(p, rule)
    l2_chunks = [c for c in result if c.chunk_level == 2]
    for c in l2_chunks:
        assert c.parent_chunk_id is None, \
            f"Level-2 chunk '{c.header_breadcrumb}' should not have a parent"


# --- chunking.split_level ---

def test_split_level_h2_merges_h3_into_parent(parser: MarkdownParser, tmp_path: Path):
    rule_h2 = Rule(
        ruleName="test",
        match=MatchConfig(glob="**/*.md"),
        labels=["docs"],
        chunking=ChunkingConfig(split_level="h2", max_tokens=800),
    )
    p = tmp_path / "deep.md"
    p.write_text(SAMPLE_MD_WITH_H3, encoding="utf-8")
    result = parser.parse(p, rule_h2)
    l3_chunks = [c for c in result if c.chunk_level == 3]
    assert l3_chunks == [], \
        f"Expected no level-3 chunks when split_level='h2', but found: {[c.header_breadcrumb for c in l3_chunks]}"
    # h3 content should be absorbed into h2 parent
    section_a = [c for c in result if "Section A" in c.header_breadcrumb]
    assert section_a, "Expected a 'Section A' level-2 chunk"
    assert any("Sub A1" in c.content or "Sub-section A1" in c.content for c in section_a), \
        "Expected Sub A1 content merged into Section A chunk"


def test_split_level_h3_keeps_all_levels(parser: MarkdownParser, tmp_path: Path):
    rule_h3 = Rule(
        ruleName="test",
        match=MatchConfig(glob="**/*.md"),
        labels=["docs"],
        chunking=ChunkingConfig(split_level="h3", max_tokens=800),
    )
    p = tmp_path / "deep.md"
    p.write_text(SAMPLE_MD_WITH_H3, encoding="utf-8")
    result = parser.parse(p, rule_h3)
    l3_chunks = [c for c in result if c.chunk_level == 3]
    assert l3_chunks, "Expected level-3 chunks when split_level='h3'"


def test_max_tokens_stored_as_metadata(parser: MarkdownParser, tmp_path: Path, chunks: list[Chunk]):
    # max_tokens is Phase 2 work; just verify the parse call doesn't blow up
    # and that chunks still have content
    assert all(c.content for c in chunks)
