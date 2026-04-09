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
    assert rule.ruleName == "default"
    assert rule.match.glob == "**/*.md"
    assert rule.exclude is False
    assert rule.labels == []
    assert rule.chunking is None


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
    doc = DocumentInfo(
        file_path="specs/auth.md",
        content="# Auth\n\nFull content here",
        frontmatter={"title": "Auth Spec", "status": "approved"},
        labels=["spec"],
        chunk_count=5,
        last_indexed="2026-04-09T12:00:00",
    )
    assert doc.frontmatter["title"] == "Auth Spec"
    assert doc.chunk_count == 5


def test_section_info():
    section = SectionInfo(
        file_path="specs/auth.md",
        header_path="Auth > OAuth > Token Refresh",
        content="Token refresh happens every 30 minutes...",
        chunk_level=3,
    )
    assert section.header_path == "Auth > OAuth > Token Refresh"


def test_status_response():
    status = StatusResponse(
        server_running=True,
        document_count=42,
        chunk_count=256,
        last_indexed="2026-04-09T12:00:00",
        ollama_available=True,
        model_loaded=True,
    )
    assert status.document_count == 42
