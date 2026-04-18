from __future__ import annotations

import pytest

from guru_core.graph_types import AnnotationCreate, AnnotationKind
from guru_graph.services.annotation_service import (
    AnnotationService,
    TargetNotFoundError,
)
from guru_graph.testing.fake_backend import FakeBackend


def _seed_target(backend: FakeBackend) -> None:
    backend.upsert_artifact(
        node_id="kb::UserService",
        label="Class",
        properties={"kb_name": "kb"},
    )


def test_create_gotcha_appends_and_returns_node():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    req = AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.GOTCHA, body="beware")
    result = svc.create(req, author="agent:test")
    assert result.id
    assert result.author == "agent:test"
    assert result.target_id == "kb::UserService"
    assert result.target_label == "Class"
    assert result.kind == AnnotationKind.GOTCHA
    assert result.body == "beware"
    assert len(backend.list_annotations_for(node_id="kb::UserService")) == 1


def test_create_summary_replaces_existing():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.SUMMARY, body="v1"),
        author="agent:test",
    )
    svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.SUMMARY, body="v2"),
        author="agent:test",
    )
    summaries = [
        a
        for a in backend.list_annotations_for(node_id="kb::UserService")
        if a["kind"] == "summary"
    ]
    assert len(summaries) == 1
    assert summaries[0]["body"] == "v2"


def test_create_multiple_gothchas_all_kept():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.GOTCHA, body="g1"),
        author="agent:test",
    )
    svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.GOTCHA, body="g2"),
        author="agent:test",
    )
    assert len(backend.list_annotations_for(node_id="kb::UserService")) == 2


def test_create_rejects_missing_target():
    backend = FakeBackend()
    backend.start()
    svc = AnnotationService(backend=backend)
    with pytest.raises(TargetNotFoundError):
        svc.create(
            AnnotationCreate(node_id="kb::missing", kind=AnnotationKind.NOTE, body="x"),
            author="agent:test",
        )


def test_create_embeds_target_snapshot():
    import json

    backend = FakeBackend()
    backend.start()
    backend.upsert_artifact(
        node_id="kb::UserService",
        label="Class",
        properties={"kb_name": "kb", "qualname": "pkg.services.UserService"},
    )
    svc = AnnotationService(backend=backend)
    result = svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.NOTE, body="hi"),
        author="agent:test",
    )
    snapshot = json.loads(result.target_snapshot_json)
    assert snapshot == {
        "target_id": "kb::UserService",
        "target_kind": "Class",
        "breadcrumb": "pkg.services.UserService",
    }


def test_delete_returns_true_once_then_false():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    node = svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.NOTE, body="hello"),
        author="agent:test",
    )
    assert svc.delete(annotation_id=node.id) is True
    assert svc.delete(annotation_id=node.id) is False


def test_list_orphans_returns_detached_annotations():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.NOTE, body="will-orphan"),
        author="agent:test",
    )
    assert svc.list_orphans() == []
    backend.orphan_annotations_for(node_ids=["kb::UserService"])
    orphans = svc.list_orphans()
    assert len(orphans) == 1


def test_reattach_orphan_reconnects():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    node = svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.NOTE, body="hello"),
        author="agent:test",
    )
    backend.orphan_annotations_for(node_ids=["kb::UserService"])
    backend.upsert_artifact(
        node_id="kb::AccountService",
        label="Class",
        properties={"kb_name": "kb"},
    )
    assert svc.reattach(annotation_id=node.id, new_node_id="kb::AccountService") is True


def test_reattach_rejects_missing_new_target():
    backend = FakeBackend()
    backend.start()
    svc = AnnotationService(backend=backend)
    with pytest.raises(TargetNotFoundError):
        svc.reattach(annotation_id="some-id", new_node_id="kb::nowhere")
