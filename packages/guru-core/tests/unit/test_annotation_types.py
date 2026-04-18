from __future__ import annotations

import pytest

from guru_core.graph_types import (
    AnnotationCreate,
    AnnotationKind,
    AnnotationNode,
    OrphanAnnotation,
    ReattachRequest,
)


def test_annotation_create_defaults():
    a = AnnotationCreate(node_id="kb::x", kind=AnnotationKind.GOTCHA, body="text")
    assert a.tags == []


def test_annotation_create_rejects_empty_body():
    with pytest.raises(ValueError):
        AnnotationCreate(node_id="kb::x", kind=AnnotationKind.NOTE, body="")


def test_annotation_create_rejects_extra_fields():
    with pytest.raises(ValueError):
        AnnotationCreate(node_id="kb::x", kind=AnnotationKind.NOTE, body="ok", extra="no")


def test_annotation_node_has_author_and_timestamps():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    n = AnnotationNode(
        id="uuid",
        target_id="kb::x",
        target_label="Class",
        kind=AnnotationKind.SUMMARY,
        body="ok",
        tags=[],
        author="agent:test",
        created_at=now,
        updated_at=now,
        target_snapshot_json='{"target_id":"kb::x"}',
    )
    assert n.author == "agent:test"
    assert n.target_id == "kb::x"


def test_annotation_node_target_id_can_be_null():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    n = AnnotationNode(
        id="uuid",
        target_id=None,
        target_label=None,
        kind=AnnotationKind.GOTCHA,
        body="orphan",
        tags=[],
        author="agent:test",
        created_at=now,
        updated_at=now,
        target_snapshot_json='{"target_id":"kb::gone"}',
    )
    assert n.target_id is None


def test_orphan_annotation_has_no_target_fields():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    o = OrphanAnnotation(
        id="uuid",
        kind=AnnotationKind.GOTCHA,
        body="beware",
        tags=[],
        author="agent:test",
        created_at=now,
        updated_at=now,
        target_snapshot_json='{"target_id":"kb::x","target_kind":"Class"}',
    )
    assert o.id == "uuid"


def test_reattach_request_shape():
    r = ReattachRequest(new_node_id="kb::y")
    assert r.new_node_id == "kb::y"


def test_reattach_request_rejects_extra():
    with pytest.raises(ValueError):
        ReattachRequest(new_node_id="kb::y", extra="no")
