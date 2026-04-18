from __future__ import annotations

from guru_server.ingestion.base import GraphEdge, GraphNode, ParseResult


def test_graph_node_minimal():
    n = GraphNode(
        node_id="alpha::docs/x.md", label="Document", properties={"language": "markdown"}
    )
    assert n.node_id == "alpha::docs/x.md"
    assert n.label == "Document"
    assert n.properties["language"] == "markdown"


def test_graph_edge_contains_no_kind():
    e = GraphEdge(from_id="a", to_id="b", rel_type="CONTAINS")
    assert e.rel_type == "CONTAINS"
    assert e.kind is None
    assert e.properties == {}


def test_graph_edge_relates_requires_kind():
    e = GraphEdge(from_id="a", to_id="b", rel_type="RELATES", kind="imports")
    assert e.rel_type == "RELATES"
    assert e.kind == "imports"


def test_parse_result_shape():
    doc = GraphNode(node_id="alpha::x.md", label="Document", properties={})
    pr = ParseResult(chunks=[], document=doc, nodes=[], edges=[])
    assert pr.document is doc
    assert pr.chunks == []
    assert pr.nodes == []
    assert pr.edges == []
