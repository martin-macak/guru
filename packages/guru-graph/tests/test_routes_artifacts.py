from __future__ import annotations

from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing.fake_backend import FakeBackend


def _client(backend: FakeBackend) -> TestClient:
    app = create_app(backend=backend)
    return TestClient(app)


def test_describe_returns_200():
    backend = FakeBackend()
    backend.start()
    backend.upsert_artifact(
        node_id="kb::UserService",
        label="Class",
        properties={"kb_name": "kb", "qualname": "pkg.services.UserService"},
    )
    client = _client(backend)
    r = client.get("/artifacts/kb::UserService")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "kb::UserService"
    assert body["label"] == "Class"
    assert body["properties"]["kb_name"] == "kb"
    assert body["annotations"] == []
    assert body["links_out"] == []
    assert body["links_in"] == []


def test_describe_returns_404_for_missing():
    backend = FakeBackend()
    backend.start()
    client = _client(backend)
    r = client.get("/artifacts/kb::ghost")
    assert r.status_code == 404


def test_describe_handles_node_id_with_slashes():
    backend = FakeBackend()
    backend.start()
    nid = "polyglot::docs/guide.md"
    backend.upsert_artifact(
        node_id=nid,
        label="MarkdownSection",
        properties={"kb_name": "polyglot"},
    )
    client = _client(backend)
    r = client.get(f"/artifacts/{nid}")
    assert r.status_code == 200
    assert r.json()["id"] == nid


def test_neighbors_returns_200_with_default_filters():
    backend = FakeBackend()
    backend.start()
    backend.upsert_artifact(node_id="kb::A", label="Module", properties={"kb_name": "kb"})
    backend.upsert_artifact(node_id="kb::B", label="Module", properties={"kb_name": "kb"})
    backend.create_relates_edge(
        from_id="kb::A",
        to_id="kb::B",
        kind="imports",
        properties={"author": "user:test", "metadata_json": "{}"},
    )
    client = _client(backend)
    r = client.get("/artifacts/kb::A/neighbors")
    assert r.status_code == 200
    body = r.json()
    assert body["node_id"] == "kb::A"
    assert [n["id"] for n in body["nodes"]] == ["kb::A", "kb::B"]
    assert len(body["edges"]) == 1


def test_neighbors_filters_by_kind_via_query_param():
    backend = FakeBackend()
    backend.start()
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
    client = _client(backend)
    r = client.get(
        "/artifacts/kb::A/neighbors",
        params={"direction": "out", "rel_type": "RELATES", "kind": "imports"},
    )
    assert r.status_code == 200
    body = r.json()
    assert [n["id"] for n in body["nodes"]] == ["kb::A", "kb::B"]


def test_find_returns_200_with_post_body():
    backend = FakeBackend()
    backend.start()
    backend.upsert_artifact(
        node_id="kb::X", label="Class", properties={"kb_name": "kb", "name": "X"}
    )
    backend.upsert_artifact(
        node_id="kb::Y", label="Class", properties={"kb_name": "kb", "name": "Y"}
    )
    client = _client(backend)
    r = client.post("/artifacts/find", json={"name": "X"})
    assert r.status_code == 200
    body = r.json()
    assert [n["id"] for n in body] == ["kb::X"]


def test_find_returns_empty_list_when_no_match():
    backend = FakeBackend()
    backend.start()
    backend.upsert_artifact(
        node_id="kb::X", label="Class", properties={"kb_name": "kb", "name": "X"}
    )
    client = _client(backend)
    r = client.post("/artifacts/find", json={"name": "nothing"})
    assert r.status_code == 200
    assert r.json() == []


def test_find_rejects_extra_fields_with_422():
    backend = FakeBackend()
    backend.start()
    client = _client(backend)
    r = client.post("/artifacts/find", json={"name": "X", "bogus": "field"})
    assert r.status_code == 422
