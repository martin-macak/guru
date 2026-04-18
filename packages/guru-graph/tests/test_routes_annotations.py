from __future__ import annotations

from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing.fake_backend import FakeBackend


def _seed(backend: FakeBackend) -> None:
    backend.upsert_artifact(
        node_id="kb::UserService",
        label="Class",
        properties={"kb_name": "kb", "qualname": "pkg.services.UserService"},
    )


def _client(backend: FakeBackend) -> TestClient:
    app = create_app(backend=backend)
    return TestClient(app)


def test_create_delete_roundtrip():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    client = _client(backend)

    r = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "gotcha", "body": "beware"},
        headers={"X-Guru-Author": "agent:test"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["author"] == "agent:test"
    assert body["target_id"] == "kb::UserService"
    aid = body["id"]

    r2 = client.delete(f"/annotations/{aid}")
    assert r2.status_code == 204

    # Deleting again returns 404
    r3 = client.delete(f"/annotations/{aid}")
    assert r3.status_code == 404


def test_create_uses_default_author_when_header_missing():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    client = _client(backend)

    r = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "note", "body": "hi"},
    )
    assert r.status_code == 201
    assert r.json()["author"] == "user:unknown"


def test_summary_replaces_existing_body():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    client = _client(backend)

    r1 = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "summary", "body": "v1"},
    )
    r2 = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "summary", "body": "v2"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["body"] == "v1"
    assert r2.json()["body"] == "v2"
    # same annotation id — replaced in place
    assert r1.json()["id"] == r2.json()["id"]


def test_orphans_endpoint_lists_detached_annotations():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    client = _client(backend)

    client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "note", "body": "will-orphan"},
    )
    assert client.get("/annotations/orphans").json() == []

    backend.orphan_annotations_for(node_ids=["kb::UserService"])
    r = client.get("/annotations/orphans")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_orphans_respects_limit():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    client = _client(backend)
    for i in range(3):
        client.post(
            "/annotations",
            json={"node_id": "kb::UserService", "kind": "note", "body": f"n{i}"},
        )
    backend.orphan_annotations_for(node_ids=["kb::UserService"])
    assert len(client.get("/annotations/orphans?limit=2").json()) == 2


def test_missing_target_returns_404_on_create():
    backend = FakeBackend()
    backend.start()
    client = _client(backend)

    r = client.post(
        "/annotations",
        json={"node_id": "kb::missing", "kind": "note", "body": "x"},
    )
    assert r.status_code == 404


def test_empty_body_rejected_422():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    client = _client(backend)

    r = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "note", "body": ""},
    )
    assert r.status_code == 422  # Pydantic min_length=1 rejects


def test_reattach_orphan_roundtrip():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    backend.upsert_artifact(
        node_id="kb::AccountService", label="Class", properties={"kb_name": "kb"}
    )
    client = _client(backend)

    create = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "note", "body": "rehome me"},
    )
    aid = create.json()["id"]
    backend.orphan_annotations_for(node_ids=["kb::UserService"])

    r = client.post(
        f"/annotations/{aid}/reattach",
        json={"new_node_id": "kb::AccountService"},
    )
    assert r.status_code == 200
    assert r.json()["target_id"] == "kb::AccountService"
    assert r.json()["target_label"] == "Class"


def test_reattach_to_missing_target_returns_404():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    client = _client(backend)

    create = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "note", "body": "x"},
    )
    backend.orphan_annotations_for(node_ids=["kb::UserService"])

    r = client.post(
        f"/annotations/{create.json()['id']}/reattach",
        json={"new_node_id": "kb::nowhere"},
    )
    assert r.status_code == 404
