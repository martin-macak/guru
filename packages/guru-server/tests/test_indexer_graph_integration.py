"""Tests for indexer <-> graph integration helpers."""

from __future__ import annotations

import pytest

from guru_core.graph_errors import GraphUnavailable
from guru_server.graph_integration import graph_or_skip, parse_result_to_payload
from guru_server.ingestion.base import GraphEdge, GraphNode, ParseResult


def test_parse_result_to_payload_roundtrip_document_only():
    doc = GraphNode(
        node_id="kb::x.md",
        label="Document",
        properties={"language": "markdown", "kb_name": "kb"},
    )
    pr = ParseResult(chunks=[], document=doc, nodes=[], edges=[])
    payload = parse_result_to_payload(pr)
    assert payload.chunks_count == 0
    assert payload.document.node_id == "kb::x.md"
    assert payload.document.label == "Document"
    assert payload.document.properties == {"language": "markdown", "kb_name": "kb"}
    assert payload.nodes == []
    assert payload.edges == []


def test_parse_result_to_payload_with_nodes_and_contains_edges():
    doc = GraphNode(node_id="kb::x.md", label="Document", properties={})
    n1 = GraphNode(node_id="kb::x.md::A", label="MarkdownSection", properties={"title": "A"})
    n2 = GraphNode(node_id="kb::x.md::B", label="MarkdownSection", properties={"title": "B"})
    e1 = GraphEdge(from_id="kb::x.md", to_id="kb::x.md::A", rel_type="CONTAINS")
    e2 = GraphEdge(from_id="kb::x.md::A", to_id="kb::x.md::B", rel_type="CONTAINS")
    pr = ParseResult(chunks=[], document=doc, nodes=[n1, n2], edges=[e1, e2])
    payload = parse_result_to_payload(pr)
    assert len(payload.nodes) == 2
    assert len(payload.edges) == 2
    assert payload.edges[0].rel_type == "CONTAINS"
    assert payload.edges[0].kind is None


def test_parse_result_to_payload_preserves_relates_kind():
    doc = GraphNode(node_id="kb::x.md", label="Document", properties={})
    e = GraphEdge(
        from_id="kb::x.md",
        to_id="kb::other",
        rel_type="RELATES",
        kind="references",
        properties={"snippet": "see other"},
    )
    pr = ParseResult(chunks=[], document=doc, nodes=[], edges=[e])
    payload = parse_result_to_payload(pr)
    assert payload.edges[0].kind == "references"
    assert payload.edges[0].properties == {"snippet": "see other"}


@pytest.mark.asyncio
async def test_graph_or_skip_swallows_graph_unavailable():
    async def _boom():
        raise GraphUnavailable("simulated")

    result = await graph_or_skip(_boom(), feature="test_2_7")
    assert result is None


@pytest.mark.asyncio
async def test_graph_or_skip_returns_value_on_success():
    async def _ok():
        return "hello"

    result = await graph_or_skip(_ok(), feature="test_2_7_ok")
    assert result == "hello"
