from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from guru_core.types import MatchConfig, Rule
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
