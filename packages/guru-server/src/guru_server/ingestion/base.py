from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from guru_core.types import Rule

@dataclass
class Chunk:
    content: str
    file_path: str
    header_breadcrumb: str
    chunk_level: int
    frontmatter: dict[str, str] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    parent_chunk_id: str | None = None
    chunk_id: str | None = None

class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path, rule: Rule) -> list[Chunk]: ...
    @abstractmethod
    def supports(self, file_path: Path) -> bool: ...
