from datetime import UTC, datetime

from guru_core.types import (
    ChunkingConfig,
    DocumentInfo,
    IndexAccepted,
    JobDetail,
    JobSummary,
    MatchConfig,
    Rule,
    SearchRequest,
    SearchResult,
    SectionInfo,
    StatusOut,
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


# --- New types for background indexing ---


def test_index_accepted_model():
    obj = IndexAccepted(job_id="abc-123", status="running", message="Indexing started")
    assert obj.job_id == "abc-123"
    assert obj.status == "running"
    assert obj.message == "Indexing started"


def test_job_summary_model():
    obj = JobSummary(
        job_id="abc-123",
        status="running",
        phase="indexing",
        files_total=15,
        files_processed=7,
        files_skipped=3,
    )
    assert obj.job_id == "abc-123"
    assert obj.phase == "indexing"


def test_job_detail_model():
    now = datetime.now(UTC)
    obj = JobDetail(
        job_id="abc-123",
        job_type="index",
        status="completed",
        phase=None,
        files_total=15,
        files_processed=12,
        files_skipped=3,
        files_deleted=1,
        chunks_created=48,
        error=None,
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    assert obj.chunks_created == 48
    assert obj.files_deleted == 1


def test_status_out_with_current_job():
    now = datetime.now(UTC)
    job = JobSummary(
        job_id="abc-123",
        status="running",
        phase="discovery",
        files_total=0,
        files_processed=0,
        files_skipped=0,
    )
    status = StatusOut(
        server_running=True,
        document_count=5,
        chunk_count=20,
        last_indexed=now,
        ollama_available=True,
        model_loaded=True,
        current_job=job,
    )
    assert status.current_job is not None
    assert status.current_job.job_id == "abc-123"


def test_status_out_without_current_job():
    status = StatusOut(
        server_running=True,
        document_count=0,
        chunk_count=0,
        last_indexed=None,
        ollama_available=True,
        model_loaded=True,
    )
    assert status.current_job is None


def test_guru_client_has_get_job_method():
    """Verify GuruClient exposes get_job()."""
    from pathlib import Path

    from guru_core.client import GuruClient

    client = GuruClient(guru_root=Path("/tmp/fake"))
    assert hasattr(client, "get_job")
    assert callable(client.get_job)
