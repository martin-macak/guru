from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from guru_core.log import setup_logging
from guru_server.app import create_app
from guru_server.bootstrap import resolve_cache_db_path, uvicorn_log_config
from guru_server.config import resolve_config
from guru_server.embed_cache import EmbeddingCache
from guru_server.embedding import OllamaEmbedder
from guru_server.startup import (
    check_model_available,
    check_ollama_installed,
    start_ollama_serve,
    stop_ollama_serve,
)
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


def _find_repo_root() -> Path:
    """Walk up from this file to the first ancestor containing `packages/`."""
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "packages").is_dir():
            return candidate
    raise RuntimeError("Could not locate repository root (no ancestor contains packages/)")


def _resolve_reload_dirs() -> list[str]:
    """Return absolute paths to source trees uvicorn should watch."""
    repo_root = _find_repo_root()
    packages = ["guru-server", "guru-core", "guru-graph"]
    return [str(repo_root / "packages" / name / "src") for name in packages]


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

    cache_db_path = resolve_cache_db_path()
    logger.info("Opening embedding cache at %s", cache_db_path)
    embed_cache = EmbeddingCache(db_path=cache_db_path)

    return create_app(
        store=store,
        embedder=embedder,
        config=config,
        project_root=str(project_root),
        embed_cache=embed_cache,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guru dev server (hot-reload, TCP-only, no federation)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
    )
    parser.add_argument("--log-file", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    setup_logging(level=args.log_level, log_file=args.log_file)

    project_root = Path(os.environ.get("GURU_PROJECT_ROOT", os.getcwd()))
    guru_dir = project_root / ".guru"
    if not guru_dir.is_dir():
        logger.error("%s does not exist. Run `guru init` first.", guru_dir)
        sys.exit(1)

    port = int(os.environ.get("GURU_DEV_PORT", "8765"))
    logger.info("Starting guru-server-dev (project_root=%s, port=%d)", project_root, port)

    check_ollama_installed()
    ollama_proc = start_ollama_serve()
    try:
        check_model_available("nomic-embed-text")
        uvicorn.run(
            "guru_server.dev:create_dev_app",
            factory=True,
            reload=True,
            reload_dirs=_resolve_reload_dirs(),
            host="127.0.0.1",
            port=port,
            log_config=uvicorn_log_config(),
        )
    finally:
        stop_ollama_serve(ollama_proc)
