from __future__ import annotations

import pytest

from guru_graph.backend import BackendHealth, BackendInfo, GraphBackendRegistry
from guru_graph.testing import FakeBackend
from guru_graph.versioning import VersionNegotiationError


@pytest.fixture
def backend() -> FakeBackend:
    b = FakeBackend()
    b.start()
    yield b
    b.stop()


def test_info_reports_fake_metadata(backend: FakeBackend):
    info = backend.info()
    assert isinstance(info, BackendInfo)
    assert info.name == "fake"


def test_health_is_healthy_after_start(backend: FakeBackend):
    h = backend.health()
    assert isinstance(h, BackendHealth)
    assert h.healthy is True


def test_upsert_kb_creates_node(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/tmp/a", tags=[], metadata_json="{}")
    rows = backend.get_kb("alpha")
    assert rows is not None
    assert rows["name"] == "alpha"
    assert rows["project_root"] == "/tmp/a"


def test_upsert_kb_is_idempotent_and_updates(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/tmp/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="alpha", project_root="/tmp/a2", tags=["x"], metadata_json="{}")
    node = backend.get_kb("alpha")
    assert node["project_root"] == "/tmp/a2"
    assert node["tags"] == ["x"]


def test_list_kbs_prefix_filter(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="alpine", project_root="/b", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/c", tags=[], metadata_json="{}")
    assert {n["name"] for n in backend.list_kbs(prefix="al")} == {"alpha", "alpine"}
    assert {n["name"] for n in backend.list_kbs()} == {"alpha", "alpine", "beta"}


def test_delete_kb_removes_node_and_links(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/b", tags=[], metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="depends_on", metadata_json="{}")
    assert backend.delete_kb("alpha") is True
    assert backend.get_kb("alpha") is None
    assert backend.list_links_for(name="beta", direction="in") == []


def test_link_creates_edge(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/b", tags=[], metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="depends_on", metadata_json="{}")
    links = backend.list_links_for(name="alpha", direction="out")
    assert len(links) == 1
    assert links[0]["to_kb"] == "beta"
    assert links[0]["kind"] == "depends_on"


def test_unlink_specific_kind(backend: FakeBackend):
    backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    backend.upsert_kb(name="beta", project_root="/b", tags=[], metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="depends_on", metadata_json="{}")
    backend.link(from_kb="alpha", to_kb="beta", kind="references", metadata_json="{}")
    assert backend.unlink(from_kb="alpha", to_kb="beta", kind="depends_on") is True
    kinds = [link["kind"] for link in backend.list_links_for(name="alpha", direction="out")]
    assert kinds == ["references"]


def test_ensure_schema_records_version(backend: FakeBackend):
    backend.ensure_schema(target_version=1)
    assert backend.info().schema_version == 1


def test_ensure_schema_refuses_downgrade(backend: FakeBackend):
    backend.ensure_schema(target_version=3)
    with pytest.raises(VersionNegotiationError):
        backend.ensure_schema(target_version=2)


def test_registry_registration():
    GraphBackendRegistry.register("fake", FakeBackend)
    assert "fake" in GraphBackendRegistry.names()
    assert GraphBackendRegistry.get("fake") is FakeBackend


# ---- Document node CRUD ----


@pytest.fixture
def fake_backend_with_kb(backend: FakeBackend) -> FakeBackend:
    backend.upsert_kb(name="local", project_root="/tmp/local", tags=[], metadata_json="{}")
    return backend


def test_document_node_upsert_and_list(fake_backend_with_kb: FakeBackend):
    fake_backend_with_kb.upsert_document_node(
        kb="local", document={"id": "a.md", "title": "A", "path": "a.md"}
    )
    nodes = fake_backend_with_kb.list_document_nodes("local")
    assert len(nodes) == 1
    assert nodes[0]["id"] == "a.md"


def test_document_node_delete(fake_backend_with_kb: FakeBackend):
    fake_backend_with_kb.upsert_document_node(
        kb="local", document={"id": "a.md", "title": "A", "path": "a.md"}
    )
    fake_backend_with_kb.delete_document_node(kb="local", doc_id="a.md")
    assert fake_backend_with_kb.list_document_nodes("local") == []


def test_document_node_upsert_is_idempotent(fake_backend_with_kb: FakeBackend):
    doc = {"id": "a.md", "title": "A", "path": "a.md"}
    fake_backend_with_kb.upsert_document_node(kb="local", document=doc)
    fake_backend_with_kb.upsert_document_node(kb="local", document={**doc, "title": "A2"})
    nodes = fake_backend_with_kb.list_document_nodes("local")
    assert len(nodes) == 1
    assert nodes[0]["title"] == "A2"
