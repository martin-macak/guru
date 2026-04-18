from __future__ import annotations

from datetime import UTC, datetime

import pytest

from guru_core.graph_types import (
    ArtifactLink,
    ArtifactLinkCreate,
    ArtifactLinkKind,
    ArtifactUnlink,
)


@pytest.mark.parametrize("kind", list(ArtifactLinkKind))
def test_artifact_link_create_round_trips_all_kinds(kind: ArtifactLinkKind):
    obj = ArtifactLinkCreate(from_id="kb::a", to_id="kb::b", kind=kind)
    assert obj.kind == kind
    assert obj.metadata == {}


def test_artifact_link_create_rejects_contains():
    with pytest.raises(ValueError):
        ArtifactLinkCreate(from_id="kb::a", to_id="kb::b", kind="contains")


def test_artifact_link_create_rejects_extra_fields():
    with pytest.raises(ValueError):
        ArtifactLinkCreate(from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.CALLS, extra="no")


def test_artifact_link_has_created_at_and_optional_author():
    now = datetime.now(UTC)
    link = ArtifactLink(
        from_id="kb::a",
        to_id="kb::b",
        kind=ArtifactLinkKind.IMPORTS,
        created_at=now,
    )
    assert link.created_at == now
    assert link.author is None


def test_artifact_link_accepts_author():
    now = datetime.now(UTC)
    link = ArtifactLink(
        from_id="kb::a",
        to_id="kb::b",
        kind=ArtifactLinkKind.REFERENCES,
        created_at=now,
        author="agent:test",
    )
    assert link.author == "agent:test"


def test_artifact_unlink_rejects_extra_fields():
    with pytest.raises(ValueError):
        ArtifactUnlink(from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.CALLS, extra="no")


def test_artifact_unlink_valid():
    u = ArtifactUnlink(from_id="kb::a", to_id="kb::b", kind=ArtifactLinkKind.IMPLEMENTS)
    assert u.from_id == "kb::a"
    assert u.kind == ArtifactLinkKind.IMPLEMENTS
