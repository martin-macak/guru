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
    # A -> B (out for A)
    backend.create_relates_edge(
        from_id="kb::A",
        to_id="kb::B",
        kind="imports",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    # C -> A (in for A)
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


def test_neighbors_returns_root_and_one_hop():
    svc, backend = _svc()
    backend.upsert_artifact(node_id="kb::A", label="Module", properties={"kb_name": "kb"})
    backend.upsert_artifact(node_id="kb::B", label="Module", properties={"kb_name": "kb"})
    backend.create_relates_edge(
        from_id="kb::A",
        to_id="kb::B",
        kind="imports",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    result = svc.neighbors(
        node_id="kb::A",
        direction="out",
        rel_type="RELATES",
        kind=None,
        depth=1,
        limit=50,
    )
    assert result.node_id == "kb::A"
    assert [n.id for n in result.nodes] == ["kb::B"]
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.from_id == "kb::A"
    assert edge.to_id == "kb::B"
    assert edge.rel_type == "RELATES"
    assert edge.kind == "imports"


def test_neighbors_respects_direction_in():
    svc, backend = _svc()
    backend.upsert_artifact(node_id="kb::A", label="Module", properties={"kb_name": "kb"})
    backend.upsert_artifact(node_id="kb::B", label="Module", properties={"kb_name": "kb"})
    backend.create_relates_edge(
        from_id="kb::A",
        to_id="kb::B",
        kind="imports",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    result = svc.neighbors(
        node_id="kb::B",
        direction="in",
        rel_type="RELATES",
        kind=None,
        depth=1,
        limit=50,
    )
    assert [n.id for n in result.nodes] == ["kb::A"]
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.from_id == "kb::A"
    assert edge.to_id == "kb::B"


def test_neighbors_respects_kind_filter():
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
        from_id="kb::A",
        to_id="kb::C",
        kind="calls",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    result = svc.neighbors(
        node_id="kb::A",
        direction="out",
        rel_type="RELATES",
        kind="imports",
        depth=1,
        limit=50,
    )
    assert [n.id for n in result.nodes] == ["kb::B"]


def test_neighbors_respects_depth():
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
        from_id="kb::B",
        to_id="kb::C",
        kind="imports",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    r1 = svc.neighbors(
        node_id="kb::A",
        direction="out",
        rel_type="RELATES",
        kind=None,
        depth=1,
        limit=50,
    )
    assert {n.id for n in r1.nodes} == {"kb::B"}
    r2 = svc.neighbors(
        node_id="kb::A",
        direction="out",
        rel_type="RELATES",
        kind=None,
        depth=2,
        limit=50,
    )
    assert {n.id for n in r2.nodes} == {"kb::B", "kb::C"}


def test_neighbors_empty_for_missing_root():
    svc, _ = _svc()
    result = svc.neighbors(
        node_id="kb::ghost",
        direction="both",
        rel_type="both",
        kind=None,
        depth=1,
        limit=50,
    )
    assert result.node_id == "kb::ghost"
    assert result.nodes == []
    assert result.edges == []


def test_find_filters_by_name():
    svc, backend = _svc()
    backend.upsert_artifact(
        node_id="kb::X", label="Class", properties={"kb_name": "kb", "name": "X"}
    )
    backend.upsert_artifact(
        node_id="kb::Y", label="Class", properties={"kb_name": "kb", "name": "Y"}
    )
    out = svc.find(ArtifactFindQuery(name="X"))
    assert [n.id for n in out] == ["kb::X"]


def test_find_filters_by_label():
    svc, backend = _svc()
    backend.upsert_artifact(node_id="kb::C1", label="Class", properties={"kb_name": "kb"})
    backend.upsert_artifact(node_id="kb::F1", label="Function", properties={"kb_name": "kb"})
    out = svc.find(ArtifactFindQuery(label="Class"))
    assert [n.id for n in out] == ["kb::C1"]


def test_find_filters_by_kb_name():
    svc, backend = _svc()
    backend.upsert_artifact(node_id="kb::A1", label="Class", properties={"kb_name": "alpha"})
    backend.upsert_artifact(node_id="kb::B1", label="Class", properties={"kb_name": "beta"})
    out = svc.find(ArtifactFindQuery(kb_name="alpha"))
    assert [n.id for n in out] == ["kb::A1"]


def test_find_returns_empty_when_no_match():
    svc, backend = _svc()
    backend.upsert_artifact(
        node_id="kb::X", label="Class", properties={"kb_name": "kb", "name": "X"}
    )
    out = svc.find(ArtifactFindQuery(name="nothing"))
    assert out == []


def test_find_respects_limit():
    svc, backend = _svc()
    for i in range(5):
        backend.upsert_artifact(
            node_id=f"kb::N{i}",
            label="Class",
            properties={"kb_name": "kb", "name": f"N{i}"},
        )
    out = svc.find(ArtifactFindQuery(limit=2))
    assert len(out) == 2
