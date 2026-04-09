from datetime import datetime

from guru_core.types import (
    MatchConfig,
    ChunkingConfig,
    Rule,
    SearchRequest,
    SearchResult,
    DocumentInfo,
    SectionInfo,
    StatusResponse,
)


def test_rule_minimal():
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    assert rule.rule_name == "default"
    assert rule.match.glob == "**/*.md"
    assert rule.exclude is False
    assert rule.labels == []
    assert rule.chunking is None


def test_rule_alias_construction():
    # Verify JSON alias "ruleName" still works for guru.json compatibility
    rule = Rule(ruleName="default", match=MatchConfig(glob="**/*.md"))
    assert rule.rule_name == "default"
    # Also verify snake_case construction works
    rule2 = Rule(rule_name="default", match=MatchConfig(glob="**/*.md"))
    assert rule2.rule_name == "default"


def test_rule_full():
    rule = Rule(
        ruleName="specs",
        match=MatchConfig(glob="specs/**/*.md"),
        exclude=False,
        labels=["spec", "requirements"],
        chunking=ChunkingConfig(max_tokens=800, split_level="h2"),
    )
    assert rule.labels == ["spec", "requirements"]
    assert rule.chunking.max_tokens == 800
    assert rule.chunking.split_level == "h2"


def test_rule_exclude():
    rule = Rule(
        ruleName="ignore-vendor",
        match=MatchConfig(glob="vendor/**"),
        exclude=True,
    )
    assert rule.exclude is True


def test_search_request_defaults():
    req = SearchRequest(query="authentication flow")
    assert req.n_results == 10
    assert req.filters == {}


def test_search_result():
    result = SearchResult(
        file_path="specs/auth.md",
        header_breadcrumb="Auth > OAuth",
        content="OAuth 2.0 flow description",
        score=0.92,
        labels=["spec"],
        chunk_level=2,
    )
    assert result.score == 0.92
    assert result.labels == ["spec"]


def test_document_info():
    dt = datetime(2026, 4, 9, 12, 0, 0)
    doc = DocumentInfo(
        file_path="specs/auth.md",
        content="# Auth\n\nFull content here",
        frontmatter={"title": "Auth Spec", "status": "approved", "tags": ["spec", "auth"]},
        labels=["spec"],
        chunk_count=5,
        last_indexed=dt,
    )
    assert doc.frontmatter["title"] == "Auth Spec"
    assert doc.frontmatter["tags"] == ["spec", "auth"]
    assert doc.chunk_count == 5
    assert doc.last_indexed == dt


def test_section_info():
    section = SectionInfo(
        file_path="specs/auth.md",
        header_path="Auth > OAuth > Token Refresh",
        content="Token refresh happens every 30 minutes...",
        chunk_level=3,
    )
    assert section.header_path == "Auth > OAuth > Token Refresh"


def test_status_response():
    dt = datetime(2026, 4, 9, 12, 0, 0)
    status = StatusResponse(
        server_running=True,
        document_count=42,
        chunk_count=256,
        last_indexed=dt,
        ollama_available=True,
        model_loaded=True,
    )
    assert status.document_count == 42
    assert status.last_indexed == dt


def test_status_response_no_last_indexed():
    status = StatusResponse(
        server_running=False,
        document_count=0,
        chunk_count=0,
        last_indexed=None,
        ollama_available=False,
        model_loaded=False,
    )
    assert status.last_indexed is None
