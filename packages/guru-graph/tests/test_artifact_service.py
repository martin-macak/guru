from __future__ import annotations

import json

from guru_core.graph_types import (
    AnnotationKind,
    ArtifactFindQuery,
    ArtifactLinkKind,
)
from guru_graph.services.artifact_service import ArtifactService
from guru_graph.testing.fake_backend import FakeBackend


def _svc() -> tuple[ArtifactService, FakeBackend]:
    backend = FakeBackend()
    backend.start()
    return ArtifactService(backend=backend), backend


def test_describe_returns_none_for_missing():
    svc, _ = _svc()
    assert svc.describe(node_id="kb::ghost") is None


def test_describe_returns_node_with_empty_annotations_and_links():
    svc, backend = _svc()
    backend.upsert_artifact(
        node_id="kb::A", label="Class", properties={"kb_name": "kb", "name": "A"}
    )
    node = svc.describe(node_id="kb::A")
    assert node is not None
    assert node.id == "kb::A"
    assert node.label == "Class"
    assert node.properties == {"kb_name": "kb", "name": "A"}
    assert node.annotations == []
    assert node.links_out == []
    assert node.links_in == []


def test_describe_includes_annotations():
    svc, backend = _svc()
    backend.upsert_artifact(node_id="kb::A", label="Class", properties={"kb_name": "kb"})
    backend.create_annotation(
        annotation_id="ann-1",
        target_id="kb::A",
        target_label="Class",
        kind="gotcha",
        body="watch out",
        tags=["careful"],
        author="agent:test",
        target_snapshot_json="{}",
    )
    node = svc.describe(node_id="kb::A")
    assert node is not None
    assert len(node.annotations) == 1
    ann = node.annotations[0]
    assert ann.kind == AnnotationKind.GOTCHA
    assert ann.body == "watch out"
    assert ann.tags == ["careful"]


def test_describe_includes_links_out_and_in():
    svc, backend = _svc()
    for nid in ("kb::A", "kb::B", "kb::C"):
        backend.upsert_artifact(node_id=nid, label="Module", properties={"kb_name": "kb"})
    backend.create_relates_edge(
        from_id="kb::A",
        to_id="kb::B",
        kind="imports",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    backend.create_relates_edge(
        from_id="kb::C",
        to_id="kb::A",
        kind="calls",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    node = svc.describe(node_id="kb::A")
    assert node is not None
    assert len(node.links_out) == 1
    assert node.links_out[0].from_id == "kb::A"
    assert node.links_out[0].to_id == "kb::B"
    assert node.links_out[0].kind == ArtifactLinkKind.IMPORTS
    assert len(node.links_in) == 1
    assert node.links_in[0].from_id == "kb::C"
    assert node.links_in[0].to_id == "kb::A"
    assert node.links_in[0].kind == ArtifactLinkKind.CALLS


def test_describe_link_includes_author_and_metadata():
    svc, backend = _svc()
    backend.upsert_artifact(node_id="kb::A", label="Module", properties={"kb_name": "kb"})
    backend.upsert_artifact(node_id="kb::B", label="Module", properties={"kb_name": "kb"})
    meta = {"note": "explicit", "line": 42}
    backend.create_relates_edge(
        from_id="kb::A",
        to_id="kb::B",
        kind="imports",
        properties={"author": "user:alice", "metadata_json": json.dumps(meta)},
    )
    node = svc.describe(node_id="kb::A")
    assert node is not None
    assert len(node.links_out) == 1
    link = node.links_out[0]
    assert link.author == "user:alice"
    assert link.metadata == meta


def test_neighbors_returns_bounded_graph():
    svc, backend = _svc()
    backend.seed_artifact(
        node_id="alpha::pkg.module",
        label="Module",
        properties={"name": "module", "qualname": "pkg.module", "kb_name": "alpha"},
    )
    backend.seed_artifact(
        node_id="alpha::pkg.module.Widget",
        label="Class",
        properties={"name": "Widget", "qualname": "pkg.module.Widget", "kb_name": "alpha"},
    )
    backend.seed_artifact(
        node_id="alpha::pkg.module.Widget.run",
        label="Method",
        properties={
            "name": "run",
            "qualname": "pkg.module.Widget.run",
            "kb_name": "alpha",
            "tags": ["entrypoint"],
        },
    )
    backend.seed_artifact_edge(
        from_id="alpha::pkg.module",
        to_id="alpha::pkg.module.Widget",
        rel_type="CONTAINS",
    )
    backend.seed_artifact_edge(
        from_id="alpha::pkg.module.Widget",
        to_id="alpha::pkg.module.Widget.run",
        rel_type="RELATES",
        kind="references",
    )
    result = svc.neighbors(
        node_id="alpha::pkg.module.Widget",
        direction="both",
        rel_type="both",
        kind=None,
        depth=1,
        limit=10,
    )
    assert [node.id for node in result.nodes] == [
        "alpha::pkg.module.Widget",
        "alpha::pkg.module",
        "alpha::pkg.module.Widget.run",
    ]
    assert {(edge.from_id, edge.to_id, edge.rel_type) for edge in result.edges} == {
        ("alpha::pkg.module", "alpha::pkg.module.Widget", "CONTAINS"),
        ("alpha::pkg.module.Widget", "alpha::pkg.module.Widget.run", "RELATES"),
    }


def test_neighbors_kind_filter_only_keeps_matching_edges():
    svc, backend = _svc()
    backend.seed_artifact(
        node_id="alpha::pkg.module.Widget",
        label="Class",
        properties={"name": "Widget", "qualname": "pkg.module.Widget", "kb_name": "alpha"},
    )
    backend.seed_artifact(
        node_id="alpha::pkg.module.Widget.run",
        label="Method",
        properties={"name": "run", "qualname": "pkg.module.Widget.run", "kb_name": "alpha"},
    )
    backend.seed_artifact_edge(
        from_id="alpha::pkg.module.Widget",
        to_id="alpha::pkg.module.Widget.run",
        rel_type="RELATES",
        kind="references",
    )
    result = svc.neighbors(
        node_id="alpha::pkg.module.Widget",
        direction="out",
        rel_type="RELATES",
        kind="references",
        depth=1,
        limit=10,
    )
    assert [node.id for node in result.nodes] == [
        "alpha::pkg.module.Widget",
        "alpha::pkg.module.Widget.run",
    ]
    assert len(result.edges) == 1
    assert result.edges[0].kind == "references"


def test_find_filters_by_name_label_and_kb():
    svc, backend = _svc()
    backend.upsert_artifact(
        node_id="kb::Widget", label="Class", properties={"kb_name": "kb", "name": "Widget"}
    )
    backend.upsert_artifact(
        node_id="kb::Service", label="Class", properties={"kb_name": "kb", "name": "Service"}
    )
    result = svc.find(
        ArtifactFindQuery(
            name="Wid",
            label="Class",
            kb_name="kb",
            limit=10,
        )
    )
    assert [node.id for node in result] == ["kb::Widget"]


def test_find_filters_by_tag():
    svc, backend = _svc()
    backend.upsert_artifact(
        node_id="kb::Run",
        label="Method",
        properties={"kb_name": "kb", "name": "run", "tags": ["entrypoint"]},
    )
    result = svc.find(ArtifactFindQuery(tag="entrypoint"))
    assert [node.id for node in result] == ["kb::Run"]
