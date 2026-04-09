from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class StatusOut(BaseModel):
    server_running: bool
    document_count: int
    chunk_count: int
    last_indexed: datetime | None
    ollama_available: bool
    model_loaded: bool


class SearchResultOut(BaseModel):
    file_path: str
    header_breadcrumb: str
    content: str
    score: float
    labels: str  # JSON string from LanceDB
    chunk_level: int


class DocumentListItem(BaseModel):
    file_path: str
    frontmatter: str  # JSON string
    labels: str  # JSON string
    chunk_count: int


class DocumentOut(BaseModel):
    file_path: str
    content: str
    frontmatter: str  # JSON string
    labels: str  # JSON string
    chunk_count: int


class SectionOut(BaseModel):
    file_path: str
    header_breadcrumb: str
    content: str
    chunk_level: int


class IndexOut(BaseModel):
    indexed: int
    documents: int
