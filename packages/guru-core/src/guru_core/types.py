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


class StatusOut(BaseModel):
    server_running: bool
    document_count: int
    chunk_count: int
    last_indexed: datetime | None
    ollama_available: bool
    model_loaded: bool


class IndexOut(BaseModel):
    indexed: int
    documents: int


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
