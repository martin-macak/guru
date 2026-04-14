from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MatchConfig(BaseModel):
    glob: str


class ChunkingConfig(BaseModel):
    max_tokens: int = 800
    split_level: str = "h2"


class Rule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rule_name: str = Field(alias="ruleName")
    match: MatchConfig
    exclude: bool = False
    labels: list[str] = Field(default_factory=list)
    chunking: ChunkingConfig | None = None


class GuruConfig(BaseModel):
    """Object-form config file. Replaces the legacy flat array of rules."""

    model_config = ConfigDict(populate_by_name=True)
    version: int = 1
    rules: list[Rule] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    n_results: int = 10
    filters: dict[str, str] = Field(default_factory=dict)


# --- API response models (canonical source of truth) ---


class SearchResultOut(BaseModel):
    file_path: str
    header_breadcrumb: str
    content: str
    score: float
    labels: list[str] = Field(default_factory=list)
    chunk_level: int


class DocumentListItem(BaseModel):
    file_path: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    chunk_count: int


class DocumentOut(BaseModel):
    file_path: str
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    chunk_count: int


class SectionOut(BaseModel):
    file_path: str
    header_breadcrumb: str
    content: str
    chunk_level: int


# --- Job models (defined before StatusOut because StatusOut references them) ---


class JobSummary(BaseModel):
    job_id: str
    status: str
    phase: str | None
    files_total: int
    files_processed: int
    files_skipped: int
    cache_hits: int = 0
    cache_misses: int = 0


class JobDetail(BaseModel):
    job_id: str
    job_type: str
    status: str
    phase: str | None
    files_total: int
    files_processed: int
    files_skipped: int
    files_deleted: int
    chunks_created: int
    cache_hits: int = 0
    cache_misses: int = 0
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# --- Embedding cache models (defined before StatusOut because StatusOut references CacheStatsOut) ---


class CacheStatsOut(BaseModel):
    path: str
    total_entries: int
    total_bytes: int
    by_model: dict[str, int] = Field(default_factory=dict)
    last_job_hits: int | None = None
    last_job_misses: int | None = None
    last_job_hit_rate: float | None = None


class CacheDeleteResult(BaseModel):
    deleted: int


class CachePruneRequest(BaseModel):
    older_than_ms: int = Field(ge=0)


class StatusOut(BaseModel):
    server_running: bool
    document_count: int
    chunk_count: int
    last_indexed: datetime | None
    ollama_available: bool
    model_loaded: bool
    current_job: JobSummary | None = None
    cache: CacheStatsOut | None = None


class IndexOut(BaseModel):
    indexed: int
    documents: int


class IndexAccepted(BaseModel):
    job_id: str
    status: str
    message: str


# --- Legacy / extended models kept for backward compatibility ---


class SearchResult(SearchResultOut):
    """Alias for SearchResultOut."""


class DocumentInfo(BaseModel):
    """Extended document model that includes last_indexed timestamp."""

    file_path: str
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    chunk_count: int
    last_indexed: datetime


class SectionInfo(BaseModel):
    """Section model using header_path naming convention."""

    file_path: str
    header_path: str
    content: str
    chunk_level: int


class StatusResponse(StatusOut):
    """Alias for StatusOut."""
