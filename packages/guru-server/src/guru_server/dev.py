from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI

from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embed_cache import EmbeddingCache
from guru_server.embedding import OllamaEmbedder
from guru_server.main import _resolve_cache_db_path
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


def create_dev_app() -> FastAPI:
    """Factory used by uvicorn's reloader worker.

    Reconstructs app dependencies on every reload. No federation
    registration, no UDS socket — pure FastAPI app over TCP.
    """
    project_root = Path(os.environ.get("GURU_PROJECT_ROOT", os.getcwd()))
    guru_dir = project_root / ".guru"
    if not guru_dir.is_dir():
        raise RuntimeError(f"{guru_dir} does not exist. Run `guru init` first.")

    config = resolve_config(project_root=project_root)

    store = VectorStore(db_path=str(guru_dir / "db"))
    embedder = OllamaEmbedder()

    cache_db_path = _resolve_cache_db_path()
    logger.info("Opening embedding cache at %s", cache_db_path)
    embed_cache = EmbeddingCache(db_path=cache_db_path)

    return create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(project_root),
        embed_cache=embed_cache,
    )
