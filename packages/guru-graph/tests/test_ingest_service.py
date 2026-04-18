from __future__ import annotations

from guru_core.graph_types import GraphEdgePayload, GraphNodePayload, ParseResultPayload
from guru_graph.services.ingest_service import IngestService
from guru_graph.testing.fake_backend import FakeBackend


def _payload(doc_id: str, sub_ids: list[str]) -> ParseResultPayload:
    doc = GraphNodePayload(
        node_id=doc_id,
        label="Document",
        properties={"kb_name": "kb", "language": "markdown"},
    )
    nodes = [
        GraphNodePayload(
            node_id=i,
            label="MarkdownSection",
            properties={"kb_name": "kb"},
        )
        for i in sub_ids
    ]
    edges = [GraphEdgePayload(from_id=doc_id, to_id=i, rel_type="CONTAINS") for i in sub_ids]
    return ParseResultPayload(chunks_count=len(sub_ids), document=doc, nodes=nodes, edges=edges)


def test_submit_creates_document_and_subnodes():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A", "kb::x.md::B"]))
    assert backend.get_artifact(node_id="kb::x.md") is not None
    assert backend.get_artifact(node_id="kb::x.md::A") is not None
    assert backend.get_artifact(node_id="kb::x.md::B") is not None
    # snapshot recorded
    assert set(backend.get_document_snapshot(doc_id="kb::x.md")) == {
        "kb::x.md::A",
        "kb::x.md::B",
    }


def test_submit_removes_deleted_subnodes_on_rerun():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A", "kb::x.md::B"]))
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A"]))  # B removed
    assert backend.get_artifact(node_id="kb::x.md::A") is not None
    assert backend.get_artifact(node_id="kb::x.md::B") is None


def test_submit_idempotent_when_payload_unchanged():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    p = _payload("kb::x.md", ["kb::x.md::A"])
    svc.submit("kb", p)
    svc.submit("kb", p)
    assert backend.get_artifact(node_id="kb::x.md::A") is not None


def test_submit_replaces_outbound_relates_rooted_at_document():
    backend = FakeBackend()
    backend.start()
    # Set up: submit doc with one section, then create a RELATES edge from
    # the section to some other artifact (simulating an imports link).
    svc = IngestService(backend=backend)
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A"]))
    backend.upsert_artifact(
        node_id="kb::other.py::mod", label="Module", properties={"kb_name": "kb"}
    )
    backend.create_relates_edge(
        from_id="kb::x.md::A",
        to_id="kb::other.py::mod",
        kind="references",
        properties={},
    )
    assert len(backend.list_relates_for(node_id="kb::x.md::A", direction="out")) == 1

    # Resubmit without the RELATES edge: the old RELATES must be wiped.
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A"]))
    assert backend.list_relates_for(node_id="kb::x.md::A", direction="out") == []


def test_delete_document_cascades_and_orphans_annotations():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A"]))
    backend.create_annotation(
        annotation_id="ann-1",
        target_id="kb::x.md::A",
        target_label="MarkdownSection",
        kind="gotcha",
        body="beware",
        tags=[],
        author="agent:test",
        target_snapshot_json='{"target_id":"kb::x.md::A","target_kind":"MarkdownSection"}',
    )

    svc.delete_document("kb", "kb::x.md")
    assert backend.get_artifact(node_id="kb::x.md::A") is None
    assert backend.get_artifact(node_id="kb::x.md") is None
    orphans = backend.list_orphans(limit=10)
    assert len(orphans) == 1
    assert orphans[0]["annotation_id"] == "ann-1"


def test_delete_nonexistent_document_is_noop():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    svc.delete_document("kb", "kb::ghost.md")  # no exception
