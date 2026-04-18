from __future__ import annotations

from pathlib import Path

from guru_core.types import Rule
from guru_server.ingestion.base import DocumentParser, GraphNode, ParseResult
from guru_server.ingestion.registry import ParserRegistry


class _FakePyParser(DocumentParser):
    name = "python"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult:
        doc = GraphNode(node_id=f"{kb_name}::{file_path}", label="Document", properties={})
        return ParseResult(chunks=[], document=doc)


class _FakeMdParser(DocumentParser):
    name = "markdown"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".md"

    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult:
        doc = GraphNode(node_id=f"{kb_name}::{file_path}", label="Document", properties={})
        return ParseResult(chunks=[], document=doc)


def test_dispatch_returns_first_match(tmp_path: Path):
    reg = ParserRegistry()
    reg.register(_FakeMdParser())
    reg.register(_FakePyParser())
    assert isinstance(reg.dispatch(tmp_path / "a.py"), _FakePyParser)
    assert isinstance(reg.dispatch(tmp_path / "a.md"), _FakeMdParser)


def test_dispatch_unknown_returns_none(tmp_path: Path):
    reg = ParserRegistry()
    reg.register(_FakePyParser())
    assert reg.dispatch(tmp_path / "a.go") is None


def test_dispatch_order_stable(tmp_path: Path):
    reg = ParserRegistry()
    md1 = _FakeMdParser()
    md2 = _FakeMdParser()
    reg.register(md1)
    reg.register(md2)
    # md1 registered first => wins
    assert reg.dispatch(tmp_path / "a.md") is md1
