from __future__ import annotations

import pytest
from pydantic import ValidationError

from guru_core.types import (
    CacheDeleteResult,
    CachePruneRequest,
    CacheStatsOut,
    GuruConfig,
    JobSummary,
    MatchConfig,
    Rule,
    StatusOut,
)


def test_guru_config_defaults():
    cfg = GuruConfig()
    assert cfg.version == 1
    assert cfg.rules == []


def test_guru_config_with_rules():
    cfg = GuruConfig(
        version=1,
        rules=[Rule(rule_name="default", match=MatchConfig(glob="**/*.md"))],
    )
    assert cfg.version == 1
    assert len(cfg.rules) == 1
    assert cfg.rules[0].rule_name == "default"


def test_guru_config_accepts_camel_case_rules():
    cfg = GuruConfig.model_validate(
        {"version": 1, "rules": [{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}]}
    )
    assert cfg.rules[0].rule_name == "docs"


def test_cache_stats_out_minimal():
    stats = CacheStatsOut(
        path="/tmp/x",
        total_entries=0,
        total_bytes=0,
        by_model={},
        last_job_hits=None,
        last_job_misses=None,
        last_job_hit_rate=None,
    )
    assert stats.total_entries == 0
    assert stats.last_job_hit_rate is None


def test_cache_delete_result_roundtrip():
    result = CacheDeleteResult(deleted=42)
    assert result.deleted == 42


def test_cache_prune_request_rejects_negative():
    with pytest.raises(ValidationError):
        CachePruneRequest(older_than_ms=-1)


def test_cache_prune_request_accepts_zero():
    req = CachePruneRequest(older_than_ms=0)
    assert req.older_than_ms == 0


def test_job_summary_has_cache_counters():
    summary = JobSummary(
        job_id="abc",
        status="completed",
        phase=None,
        files_total=1,
        files_processed=1,
        files_skipped=0,
        cache_hits=3,
        cache_misses=2,
    )
    assert summary.cache_hits == 3
    assert summary.cache_misses == 2


def test_job_summary_cache_counters_default_zero():
    summary = JobSummary(
        job_id="abc",
        status="completed",
        phase=None,
        files_total=0,
        files_processed=0,
        files_skipped=0,
    )
    assert summary.cache_hits == 0
    assert summary.cache_misses == 0


def test_status_out_cache_defaults_to_none():
    from datetime import UTC, datetime

    status = StatusOut(
        server_running=True,
        document_count=0,
        chunk_count=0,
        last_indexed=datetime.now(UTC),
        ollama_available=True,
        model_loaded=True,
    )
    assert status.cache is None
