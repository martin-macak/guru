from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from guru_server.api import api_router
from guru_server.embedding import OllamaEmbedder
from guru_server.indexer import BackgroundIndexer
from guru_server.jobs import JobRegistry
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore


def create_app(
    store: VectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    config: list | None = None,
    project_root: str | None = None,
    auto_index: bool = True,
) -> FastAPI:
    """Create the FastAPI application.

    Accepts optional overrides for testing. In production these are
    created from the server's startup sequence.

    Args:
        auto_index: If True (default), auto-index on startup and start
            the file watcher. Set to False in tests that don't need it.
    """
    app = FastAPI(title="Guru Server", version="0.1.0")
    app.state.store = store
    app.state.embedder = embedder
    app.state.config = config or []
    app.state.project_root = project_root or "."
    app.state.last_indexed = None
    app.state.job_registry = JobRegistry()

    # Create manifest using the same LanceDB connection as the store
    if store is not None and hasattr(store, "db"):
        app.state.manifest = FileManifest(store.db)
    else:
        app.state.manifest = None

    # Create indexer if we have all dependencies
    if store is not None and embedder is not None and app.state.manifest is not None:
        app.state.indexer = BackgroundIndexer(
            store=store,
            manifest=app.state.manifest,
            embedder=embedder,
            config=app.state.config,
            project_root=Path(app.state.project_root),
        )
    else:
        app.state.indexer = None

    app.include_router(api_router)
    return app
