from __future__ import annotations

from fastapi import FastAPI

from guru_server.api import api_router
from guru_server.embedding import OllamaEmbedder
from guru_server.storage import VectorStore


def create_app(
    store: VectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    config: list | None = None,
    project_root: str | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Accepts optional overrides for testing. In production these are
    created from the server's startup sequence.
    """
    app = FastAPI(title="Guru Server", version="0.1.0")
    app.state.store = store
    app.state.embedder = embedder
    app.state.config = config or []
    app.state.project_root = project_root or "."
    app.include_router(api_router)
    return app
