from __future__ import annotations

from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing.fake_backend import FakeBackend


def _seed(backend: FakeBackend) -> tuple[str, str]:
    from_id = "kb::ModuleA"
    to_id = "kb::ModuleB"
    backend.upsert_artifact(node_id=from_id, label="Class", properties={"kb_name": "kb"})
    backend.upsert_artifact(node_id=to_id, label="Class", properties={"kb_name": "kb"})
    return from_id, to_id


def _client(backend: FakeBackend) -> TestClient:
    app = create_app(backend=backend)
    return TestClient(app)


def test_create_relates_returns_201_and_body():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed(backend)
    client = _client(backend)

    r = client.post(
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "imports"},
        headers={"X-Guru-Author": "agent:test"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["from_id"] == from_id
    assert body["to_id"] == to_id
    assert body["kind"] == "imports"
    assert body["author"] == "agent:test"


def test_create_relates_uses_default_author_when_header_missing():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed(backend)
    client = _client(backend)

    r = client.post(
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "calls"},
    )
    assert r.status_code == 201
    assert r.json()["author"] == "user:unknown"


def test_create_relates_passes_x_guru_author_header():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed(backend)
    client = _client(backend)

    r = client.post(
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "references"},
        headers={"X-Guru-Author": "user:alice"},
    )
    assert r.status_code == 201
    assert r.json()["author"] == "user:alice"


def test_create_relates_404_on_missing_from():
    backend = FakeBackend()
    backend.start()
    _, to_id = _seed(backend)
    client = _client(backend)

    r = client.post(
        "/relates",
        json={"from_id": "kb::NoSuchModule", "to_id": to_id, "kind": "imports"},
    )
    assert r.status_code == 404


def test_create_relates_404_on_missing_to():
    backend = FakeBackend()
    backend.start()
    from_id, _ = _seed(backend)
    client = _client(backend)

    r = client.post(
        "/relates",
        json={"from_id": from_id, "to_id": "kb::NoSuchModule", "kind": "imports"},
    )
    assert r.status_code == 404


def test_create_relates_422_on_unknown_kind():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed(backend)
    client = _client(backend)

    r = client.post(
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "owns"},
    )
    assert r.status_code == 422


def test_create_relates_422_on_missing_required_field():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed(backend)
    client = _client(backend)

    r = client.post(
        "/relates",
        json={"from_id": from_id, "to_id": to_id},  # missing "kind"
    )
    assert r.status_code == 422


def test_delete_relates_204_then_404():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed(backend)
    client = _client(backend)

    # Create the link first
    client.post(
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "implements"},
    )

    # First delete: 204
    r1 = client.request(
        "DELETE",
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "implements"},
    )
    assert r1.status_code == 204

    # Second delete: 404
    r2 = client.request(
        "DELETE",
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "implements"},
    )
    assert r2.status_code == 404


def test_delete_relates_422_on_unknown_kind():
    backend = FakeBackend()
    backend.start()
    from_id, to_id = _seed(backend)
    client = _client(backend)

    r = client.request(
        "DELETE",
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": "owns"},
    )
    assert r.status_code == 422
