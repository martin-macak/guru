"""Integration smoke test: init -> index -> search without real Ollama."""

import json

import pytest
from fastapi.testclient import TestClient

from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embedding import OllamaEmbedder
from guru_server.storage import VectorStore


@pytest.fixture
def project(tmp_path):
    """Set up a fake guru project with some markdown files."""
    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    (guru_dir / "db").mkdir()

    # Config
    config = tmp_path / "guru.json"
    config.write_text(
        json.dumps(
            [
                {"ruleName": "default", "match": {"glob": "**/*.md"}},
            ]
        )
    )

    # Sample docs
    docs = tmp_path / "docs"
    docs.mkdir()

    (docs / "auth.md").write_text("""\
---
title: Authentication
status: approved
---

# Authentication

Overview of authentication.

## OAuth 2.0

We use OAuth 2.0 for external clients.

## API Keys

Internal services use API keys.
""")

    (docs / "rbac.md").write_text("""\
---
title: RBAC
status: draft
---

# Role-Based Access Control

Users have roles. Roles have permissions.

## Admin Role

Admins can do everything.
""")

    return tmp_path


@pytest.fixture
def mock_embedder():
    embedder = OllamaEmbedder()
    # Return deterministic fake embeddings — slightly different per call
    call_count = 0

    async def fake_embed(text):
        nonlocal call_count
        call_count += 1
        # Create slightly different vectors so search has variation
        vec = [0.1] * 768
        vec[call_count % 768] = 1.0
        return vec

    async def batch_embed(texts):
        results = []
        for t in texts:
            results.append(await fake_embed(t))
        return results

    embedder.embed = fake_embed
    embedder.embed_batch = batch_embed
    return embedder


@pytest.fixture
def client(project, mock_embedder):
    config = resolve_config(project_root=project)
    store = VectorStore(db_path=str(project / ".guru" / "db"))
    app = create_app(
        store=store,
        embedder=mock_embedder,
        config=config,
        project_root=str(project),
    )
    return TestClient(app)


def test_full_pipeline(client):
    # 1. Status — should be empty
    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["chunk_count"] == 0

    # 2. Index
    resp = client.post("/index", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["documents"] >= 2
    assert data["indexed"] >= 4  # At least a few chunks per doc

    # 3. Status — should have data now
    resp = client.get("/status")
    assert resp.json()["chunk_count"] > 0

    # 4. Search
    resp = client.post("/search", json={"query": "OAuth authentication"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0

    # 5. List documents
    resp = client.get("/documents")
    assert resp.status_code == 200
    docs = resp.json()
    paths = [d["file_path"] for d in docs]
    assert any("auth.md" in p for p in paths)
    assert any("rbac.md" in p for p in paths)

    # 6. Get document
    auth_path = next(p for p in paths if "auth.md" in p)
    resp = client.get(f"/documents/{auth_path}")
    assert resp.status_code == 200
    assert "Authentication" in resp.json()["content"]
