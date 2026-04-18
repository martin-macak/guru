"""Test ProtobufParser — proves the DocumentParser protocol is a pure
extension point: adding a new file type requires only registering a new
parser, no core changes.

This parser lives under ``tests/e2e/fixtures`` (not in any guru package),
so it is loaded purely from the test side.
"""

from __future__ import annotations

from pathlib import Path

from guru_core.types import Rule
from guru_server.ingestion.base import (
    Chunk,
    DocumentParser,
    GraphNode,
    ParseResult,
)


class ProtobufParser(DocumentParser):
    # Class-level call log — BDD asserts on this. Cleared per scenario.
    parse_call_log: list[str] = []

    @property
    def name(self) -> str:
        return "protobuf"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".proto"

    def parse(
        self, file_path: Path, rule: Rule, *, kb_name: str, rel_path: str = ""
    ) -> ParseResult:
        if not rel_path:
            rel_path = file_path.name
        ProtobufParser.parse_call_log.append(rel_path)
        doc_id = f"{kb_name}::{rel_path}"
        document = GraphNode(
            node_id=doc_id,
            label="Document",
            properties={
                "kb_name": kb_name,
                "relative_path": rel_path,
                "absolute_path": str(file_path),
                "language": "protobuf",
                "file_type": "schema",
                "parser_name": "protobuf",
                "size_bytes": file_path.stat().st_size,
            },
        )
        chunks = [
            Chunk(
                content=file_path.read_text(),
                file_path=str(file_path),
                header_breadcrumb="proto",
                chunk_level=1,
                kind="code",
                language="protobuf",
                parent_document_id=doc_id,
                artifact_qualname=f"{doc_id}::root",
            )
        ]
        return ParseResult(chunks=chunks, document=document, nodes=[], edges=[])
