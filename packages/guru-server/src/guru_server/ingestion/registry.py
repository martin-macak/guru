"""Parser registry — the extension point for new ingestion formats.

Order of registration matters: first match wins. Adding a new parser is a
single `register()` call at server startup (see guru_server.main). No core
change is required.
"""

from __future__ import annotations

from pathlib import Path

from .base import DocumentParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[DocumentParser] = []

    def register(self, parser: DocumentParser) -> None:
        self._parsers.append(parser)

    def dispatch(self, file_path: Path) -> DocumentParser | None:
        for p in self._parsers:
            if p.supports(file_path):
                return p
        return None

    @property
    def all(self) -> tuple[DocumentParser, ...]:
        return tuple(self._parsers)
