from __future__ import annotations

import pytest

from guru_core.graph_types import KbLinkCreate, KbUpsert, LinkKind
from guru_graph.services.kb_service import KbNotFoundError, KbService
from guru_graph.testing import FakeBackend


@pytest.fixture
def service() -> KbService:
    backend = FakeBackend()
    backend.start()
    svc = KbService(backend=backend)
    yield svc
    backend.stop()


def test_upsert_returns_node_with_timestamps(service: KbService):
    node = service.upsert(KbUpsert(name="alpha", project_root="/a", tags=["app"]))
    assert node.name == "alpha"
    assert node.tags == ["app"]
    assert node.created_at == node.updated_at


def test_upsert_is_idempotent(service: KbService):
    first = service.upsert(KbUpsert(name="alpha", project_root="/a"))
    second = service.upsert(KbUpsert(name="alpha", project_root="/a2"))
    assert first.created_at == second.created_at
    assert second.updated_at >= first.updated_at
    assert second.project_root == "/a2"


def test_get_returns_none_when_missing(service: KbService):
    assert service.get("unknown") is None


def test_list_prefix(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="alpine", project_root="/b"))
    service.upsert(KbUpsert(name="beta", project_root="/c"))
    assert {n.name for n in service.list(prefix="al")} == {"alpha", "alpine"}


def test_delete_missing_returns_false(service: KbService):
    assert service.delete("nope") is False


def test_link_requires_existing_endpoints(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    with pytest.raises(KbNotFoundError):
        service.link(from_kb="alpha", req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))


def test_link_and_list(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="beta", project_root="/b"))
    service.link(from_kb="alpha", req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))
    outs = service.list_links(name="alpha", direction="out")
    assert len(outs) == 1
    assert outs[0].to_kb == "beta"
    assert outs[0].kind is LinkKind.DEPENDS_ON


def test_unlink(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="beta", project_root="/b"))
    service.link(from_kb="alpha", req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))
    assert service.unlink(from_kb="alpha", to_kb="beta", kind=LinkKind.DEPENDS_ON) is True


def test_delete_cascades_links(service: KbService):
    service.upsert(KbUpsert(name="alpha", project_root="/a"))
    service.upsert(KbUpsert(name="beta", project_root="/b"))
    service.link(from_kb="alpha", req=KbLinkCreate(to_kb="beta", kind=LinkKind.DEPENDS_ON))
    assert service.delete("alpha") is True
    assert service.list_links(name="beta", direction="in") == []
