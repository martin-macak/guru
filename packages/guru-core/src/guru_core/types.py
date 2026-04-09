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


class SearchResult(BaseModel):
    file_path: str
    header_breadcrumb: str
    content: str
    score: float
    labels: list[str] = Field(default_factory=list)
    chunk_level: int


class DocumentInfo(BaseModel):
    file_path: str
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    chunk_count: int
    last_indexed: datetime


class SectionInfo(BaseModel):
    file_path: str
    header_path: str
    content: str
    chunk_level: int


class StatusResponse(BaseModel):
    server_running: bool
    document_count: int
    chunk_count: int
    last_indexed: datetime | None
    ollama_available: bool
    model_loaded: bool
