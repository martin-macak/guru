from __future__ import annotations

import json

import pytest

from guru_core.graph_types import ArtifactLinkCreate, ArtifactLinkKind
from guru_graph.services.relates_service import EndpointNotFoundError, RelatesService
from guru_graph.testing.fake_backend import FakeBackend


def _seed_two(backend: FakeBackend) -> tuple[str, str]:
    from_id = "kb::ModuleA"
    to_id = "kb::ModuleB"
    backend.upsert_artifact(node_id=from_id, label="Class", properties={"kb_name": "kb"})
    backend.upsert_artifact(node_id=to_id, label="Class", properties={"kb_name": "kb"})
    return from_id, to_id


def test_create_link_returns_artifact_link():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed_two(backend)
    svc = RelatesService(backend=backend)
    req = ArtifactLinkCreate(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind.IMPORTS)
    result = svc.create(req, author="agent:test")
    assert result.from_id == from_id
    assert result.to_id == to_id
    assert result.kind == ArtifactLinkKind.IMPORTS
    assert result.author == "agent:test"
    assert result.metadata == {}
    assert result.created_at is not None


def test_create_persists_to_backend():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed_two(backend)
    svc = RelatesService(backend=backend)
    req = ArtifactLinkCreate(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind.CALLS)
    svc.create(req, author="agent:test")
    relates = backend.list_relates_for(node_id=from_id, direction="out")
    assert len(relates) == 1
    assert relates[0]["kind"] == ArtifactLinkKind.CALLS.value


def test_create_rejects_missing_from_endpoint():
    backend = FakeBackend()
    backend.start()
    to_id = "kb::ModuleB"
    backend.upsert_artifact(node_id=to_id, label="Class", properties={"kb_name": "kb"})
    svc = RelatesService(backend=backend)
    req = ArtifactLinkCreate(from_id="kb::Missing", to_id=to_id, kind=ArtifactLinkKind.IMPORTS)
    with pytest.raises(EndpointNotFoundError, match="kb::Missing"):
        svc.create(req, author="agent:test")


def test_create_rejects_missing_to_endpoint():
    backend = FakeBackend()
    backend.start()
    from_id = "kb::ModuleA"
    backend.upsert_artifact(node_id=from_id, label="Class", properties={"kb_name": "kb"})
    svc = RelatesService(backend=backend)
    req = ArtifactLinkCreate(from_id=from_id, to_id="kb::Missing", kind=ArtifactLinkKind.IMPORTS)
    with pytest.raises(EndpointNotFoundError, match="kb::Missing"):
        svc.create(req, author="agent:test")


def test_delete_returns_true_then_false():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed_two(backend)
    svc = RelatesService(backend=backend)
    req = ArtifactLinkCreate(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind.REFERENCES)
    svc.create(req, author="agent:test")
    assert svc.delete(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind.REFERENCES) is True
    assert svc.delete(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind.REFERENCES) is False


def test_create_with_metadata_persists_metadata_json():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed_two(backend)
    svc = RelatesService(backend=backend)
    meta = {"note": "explicit import", "line": 42}
    req = ArtifactLinkCreate(
        from_id=from_id, to_id=to_id, kind=ArtifactLinkKind.IMPORTS, metadata=meta
    )
    svc.create(req, author="agent:test")
    relates = backend.list_relates_for(node_id=from_id, direction="out")
    assert len(relates) == 1
    stored_meta = json.loads(relates[0]["properties"]["metadata_json"])
    assert stored_meta == meta


@pytest.mark.parametrize("kind", list(ArtifactLinkKind))
def test_create_each_kind(kind: ArtifactLinkKind):
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed_two(backend)
    svc = RelatesService(backend=backend)
    req = ArtifactLinkCreate(from_id=from_id, to_id=to_id, kind=kind)
    result = svc.create(req, author="agent:test")
    assert result.kind == kind
