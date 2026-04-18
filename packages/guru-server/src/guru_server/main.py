from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from dataclasses import replace
from pathlib import Path

import uvicorn
from platformdirs import user_cache_dir

from guru_core.config import federation_dir
from guru_core.log import setup_logging
from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embed_cache import EmbeddingCache
from guru_server.embedding import OllamaEmbedder
from guru_server.federation import FederationRegistry
from guru_server.startup import (
    check_model_available,
    check_ollama_installed,
    start_ollama_serve,
    stop_ollama_serve,
)
from guru_server.storage import VectorStore
from guru_server.web_runtime import bind_web_listener_sockets

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guru knowledge-base server")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Log level (default: INFO, overrides GURU_LOG_LEVEL env var)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Path to log file (enables rotating file handler)",
    )
    return parser.parse_args(argv)


def _uvicorn_log_config() -> dict:
    """Build a uvicorn log_config that propagates to the root logger.

    By setting propagate=True and removing custom handlers, uvicorn logs
    flow through the root logger's handlers (stderr + optional file),
    giving a unified log format and destination.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "loggers": {
            "uvicorn": {"level": "INFO", "propagate": True},
            "uvicorn.error": {"level": "INFO", "propagate": True},
            "uvicorn.access": {"level": "INFO", "propagate": True},
        },
    }


def _resolve_cache_db_path() -> Path:
    """Return the filesystem path to the embedding cache SQLite file.

    Honors the GURU_EMBED_CACHE_PATH environment variable for test isolation.
    Otherwise uses platformdirs.user_cache_dir('guru') / 'embeddings.db'.
    """
    env = os.environ.get("GURU_EMBED_CACHE_PATH")
    if env:
        return Path(env)
    return Path(user_cache_dir("guru")) / "embeddings.db"


def main(argv: list[str] | None = None):
    args = _parse_args(argv)
    setup_logging(level=args.log_level, log_file=args.log_file, daemon=bool(args.log_file))

    project_root = os.environ.get("GURU_PROJECT_ROOT", os.getcwd())
    guru_dir = Path(project_root) / ".guru"

    if not guru_dir.is_dir():
        logger.error("%s does not exist. Run `guru init` first.", guru_dir)
        sys.exit(1)

    logger.info("Starting guru-server (project_root=%s)", project_root)

    # Preflight checks + startup
    check_ollama_installed()
    ollama_proc = start_ollama_serve()
    try:
        check_model_available("nomic-embed-text")

        config = resolve_config(project_root=Path(project_root))

        # Federation: register this server
        project_name = config.name or Path(project_root).name
        fed_registry: FederationRegistry | None = None
        try:
            fed_registry = FederationRegistry(
                name=project_name,
                pid=os.getpid(),
                socket_path=str(guru_dir / "guru.sock"),
                project_root=project_root,
                federation_dir=federation_dir(),
            )
            fed_registry.register()
        except OSError:
            logger.warning("Federation registration failed — running standalone", exc_info=True)
            fed_registry = None

        store = VectorStore(db_path=str(guru_dir / "db"))
        embedder = OllamaEmbedder()

        cache_db_path = _resolve_cache_db_path()
        logger.info("Opening embedding cache at %s", cache_db_path)
        embed_cache = EmbeddingCache(db_path=cache_db_path)

        app = create_app(
            store=store,
            embedder=embedder,
            config=config,
            project_root=project_root,
            embed_cache=embed_cache,
        )

        socket_path = str(guru_dir / "guru.sock")
        pid_path = guru_dir / "guru.pid"
        sockets: list[socket.socket] | None = None

        pid_path.write_text(str(os.getpid()))
        logger.info("Listening on %s (PID %d)", socket_path, os.getpid())

        try:
            if app.state.web_runtime.available and app.state.web_runtime.port is not None:
                try:
                    sockets = bind_web_listener_sockets(
                        uds_path=Path(socket_path),
                        port=app.state.web_runtime.port,
                    )
                except OSError:
                    logger.exception("Failed to start web listener; continuing without it")
                    app.state.web_runtime = replace(
                        app.state.web_runtime,
                        available=False,
                        url=None,
                        port=None,
                        assets_dir=None,
                        reason="listen_failed",
                    )

            if sockets is None:
                uvicorn.run(
                    app,
                    uds=socket_path,
                    log_config=_uvicorn_log_config(),
                )
            else:
                server = uvicorn.Server(uvicorn.Config(app, log_config=_uvicorn_log_config()))
                server.run(sockets=sockets)
        finally:
            if sockets is not None:
                for sock in sockets:
                    sock.close()
            if fed_registry is not None:
                fed_registry.deregister()
            pid_path.unlink(missing_ok=True)
            Path(socket_path).unlink(missing_ok=True)
            logger.info("Server shut down")
    finally:
        stop_ollama_serve(ollama_proc)
