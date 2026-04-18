"""Unit tests for artifact ops on FakeBackend (in-memory).

These exercise the ArtifactOpsBackend protocol methods on FakeBackend
without touching Neo4j. They cover:
- Document/artifact upsert + get
- CONTAINS edges + neighbor walks + subtree collection
- RELATES edges + list/remove
- Annotation lifecycle (create, list, delete, orphan, reattach, replace)
- Snapshot round-trip
- find_artifacts filters
"""

from __future__ import annotations

import pytest

from guru_graph.testing import FakeBackend


@pytest.fixture
def backend() -> FakeBackend:
    b = FakeBackend()
    b.start()
    yield b
    b.stop()


def test_upsert_document_and_get_artifact(backend: FakeBackend):
    backend.upsert_document(
        node_id="doc-1", label="Document", properties={"path": "/a.py", "kb_name": "alpha"}
    )
    got = backend.get_artifact(node_id="doc-1")
    assert got == {
        "id": "doc-1",
        "label": "Document",
        "properties": {"path": "/a.py", "kb_name": "alpha"},
    }


def test_upsert_artifact_and_contains_edge_and_list_neighbors(backend: FakeBackend):
    backend.upsert_document(node_id="doc", label="Document", properties={})
    backend.upsert_artifact(node_id="fn", label="Function", properties={"name": "f"})
    backend.create_contains_edge(from_id="doc", to_id="fn")
    neighbors = backend.list_neighbors(
        node_id="doc",
        direction="out",
        rel_type="CONTAINS",
        kind=None,
        depth=1,
        limit=10,
    )
    assert [n["id"] for n in neighbors] == ["fn"]
    assert neighbors[0]["rel_type"] == "CONTAINS"
    assert neighbors[0]["label"] == "Function"


def test_delete_artifact_with_descendants_returns_full_subtree(backend: FakeBackend):
    backend.upsert_document(node_id="grand", label="Document", properties={})
    backend.upsert_artifact(node_id="parent", label="Class", properties={})
    backend.upsert_artifact(node_id="child", label="Method", properties={})
    backend.create_contains_edge(from_id="grand", to_id="parent")
    backend.create_contains_edge(from_id="parent", to_id="child")
    ids = backend.delete_artifact_with_descendants(node_id="grand")
    assert set(ids) == {"grand", "parent", "child"}


def test_delete_artifact_removes_connected_edges(backend: FakeBackend):
    backend.upsert_artifact(node_id="a", label="Class", properties={})
    backend.upsert_artifact(node_id="b", label="Function", properties={})
    backend.create_contains_edge(from_id="a", to_id="b")
    backend.delete_artifact(node_id="a")
    assert backend.get_artifact(node_id="a") is None
    # Edge referencing deleted id must be gone.
    assert (
        backend.list_neighbors(
            node_id="b", direction="in", rel_type="CONTAINS", kind=None, depth=1, limit=10
        )
        == []
    )


def test_create_and_list_annotation(backend: FakeBackend):
    backend.upsert_artifact(node_id="fn", label="Function", properties={})
    backend.create_annotation(
        annotation_id="ann-1",
        target_id="fn",
        target_label="Function",
        kind="note",
        body="hello",
        tags=["x"],
        author="me",
        target_snapshot_json="{}",
    )
    anns = backend.list_annotations_for(node_id="fn")
    assert len(anns) == 1
    assert anns[0]["annotation_id"] == "ann-1"
    assert anns[0]["body"] == "hello"
    assert anns[0]["tags"] == ["x"]


def test_delete_annotation_returns_true_then_false(backend: FakeBackend):
    backend.upsert_artifact(node_id="fn", label="Function", properties={})
    backend.create_annotation(
        annotation_id="ann-1",
        target_id="fn",
        target_label="Function",
        kind="note",
        body="b",
        tags=[],
        author="me",
        target_snapshot_json="{}",
    )
    assert backend.delete_annotation(annotation_id="ann-1") is True
    assert backend.delete_annotation(annotation_id="ann-1") is False


def test_orphan_annotations_for_preserves_annotation_and_unsets_target(backend: FakeBackend):
    backend.upsert_artifact(node_id="fn", label="Function", properties={})
    backend.create_annotation(
        annotation_id="ann-1",
        target_id="fn",
        target_label="Function",
        kind="note",
        body="b",
        tags=[],
        author="me",
        target_snapshot_json="{}",
    )
    backend.orphan_annotations_for(node_ids=["fn"])
    assert backend.list_annotations_for(node_id="fn") == []
    orphans = backend.list_orphans(limit=10)
    assert len(orphans) == 1
    assert orphans[0]["annotation_id"] == "ann-1"
    assert orphans[0]["target_id"] is None


def test_list_orphans_skips_attached_annotations(backend: FakeBackend):
    backend.upsert_artifact(node_id="fn", label="Function", properties={})
    backend.create_annotation(
        annotation_id="ann-attached",
        target_id="fn",
        target_label="Function",
        kind="note",
        body="b",
        tags=[],
        author="me",
        target_snapshot_json="{}",
    )
    assert backend.list_orphans(limit=10) == []


def test_reattach_orphan_sets_new_target(backend: FakeBackend):
    backend.upsert_artifact(node_id="fn-old", label="Function", properties={})
    backend.upsert_artifact(node_id="fn-new", label="Function", properties={})
    backend.create_annotation(
        annotation_id="ann",
        target_id="fn-old",
        target_label="Function",
        kind="note",
        body="b",
        tags=[],
        author="me",
        target_snapshot_json="{}",
    )
    backend.orphan_annotations_for(node_ids=["fn-old"])
    assert backend.reattach_orphan(annotation_id="ann", new_target_id="fn-new") is True
    assert backend.list_annotations_for(node_id="fn-new")[0]["annotation_id"] == "ann"
    # Re-attaching an already-attached annotation is not allowed.
    assert backend.reattach_orphan(annotation_id="ann", new_target_id="fn-old") is False


def test_replace_summary_annotation_updates_in_place(backend: FakeBackend):
    backend.upsert_artifact(node_id="fn", label="Function", properties={})
    backend.replace_summary_annotation(
        annotation_id="sum-1",
        target_id="fn",
        target_label="Function",
        body="v1",
        tags=[],
        author="me",
        target_snapshot_json="{}",
    )
    backend.replace_summary_annotation(
        annotation_id="sum-1",
        target_id="fn",
        target_label="Function",
        body="v2",
        tags=["latest"],
        author="me",
        target_snapshot_json="{}",
    )
    anns = backend.list_annotations_for(node_id="fn")
    assert len(anns) == 1
    assert anns[0]["body"] == "v2"
    assert anns[0]["tags"] == ["latest"]
    assert anns[0]["kind"] == "summary"


def test_relates_edge_create_and_delete_and_list_relates_for(backend: FakeBackend):
    backend.upsert_artifact(node_id="a", label="Module", properties={})
    backend.upsert_artifact(node_id="b", label="Module", properties={})
    backend.create_relates_edge(from_id="a", to_id="b", kind="imports", properties={"via": "ast"})
    out = backend.list_relates_for(node_id="a", direction="out")
    assert len(out) == 1
    assert out[0]["to_id"] == "b"
    assert out[0]["kind"] == "imports"
    assert out[0]["properties"] == {"via": "ast"}
    assert backend.delete_relates_edge(from_id="a", to_id="b", kind="imports") is True
    assert backend.list_relates_for(node_id="a", direction="out") == []


def test_remove_outbound_relates_rooted_at_wipes_descendants_relates(backend: FakeBackend):
    backend.upsert_document(node_id="doc", label="Document", properties={})
    backend.upsert_artifact(node_id="child", label="Function", properties={})
    backend.upsert_artifact(node_id="other", label="Function", properties={})
    backend.create_contains_edge(from_id="doc", to_id="child")
    backend.create_relates_edge(from_id="child", to_id="other", kind="calls", properties={})
    backend.remove_outbound_relates_rooted_at(doc_id="doc")
    assert backend.list_relates_for(node_id="child", direction="out") == []


def test_find_artifacts_filters_by_label_and_kb_name(backend: FakeBackend):
    backend.upsert_artifact(node_id="c1", label="Class", properties={"kb_name": "alpha"})
    backend.upsert_artifact(node_id="c2", label="Class", properties={"kb_name": "beta"})
    backend.upsert_artifact(node_id="f1", label="Function", properties={"kb_name": "alpha"})
    alpha_classes = backend.find_artifacts(
        name=None,
        qualname_prefix=None,
        label="Class",
        tag=None,
        kb_name="alpha",
        limit=10,
    )
    assert [a["id"] for a in alpha_classes] == ["c1"]


def test_get_document_snapshot_and_set_document_snapshot_roundtrip(backend: FakeBackend):
    backend.upsert_document(node_id="doc", label="Document", properties={})
    assert backend.get_document_snapshot(doc_id="doc") == []
    backend.set_document_snapshot(doc_id="doc", node_ids=["a", "b", "c"])
    assert backend.get_document_snapshot(doc_id="doc") == ["a", "b", "c"]
    # Returned list is independent of internal storage.
    snap = backend.get_document_snapshot(doc_id="doc")
    snap.append("mut")
    assert backend.get_document_snapshot(doc_id="doc") == ["a", "b", "c"]
