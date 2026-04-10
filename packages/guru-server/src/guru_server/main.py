from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn

from guru_core.log import DATE_FORMAT, LOG_FORMAT, setup_logging
from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embedding import OllamaEmbedder
from guru_server.startup import (
    check_model_available,
    check_ollama_installed,
    start_ollama_serve,
    stop_ollama_serve,
)
from guru_server.storage import VectorStore

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


def _uvicorn_log_config(formatter_fmt: str, date_fmt: str) -> dict:
    """Build a uvicorn log_config that reuses our log format."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"fmt": formatter_fmt, "datefmt": date_fmt},
            "access": {"fmt": formatter_fmt, "datefmt": date_fmt},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {
                "handlers": ["access"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }


def main():
    args = _parse_args()
    setup_logging(level=args.log_level, log_file=args.log_file)

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
        store = VectorStore(db_path=str(guru_dir / "db"))
        embedder = OllamaEmbedder()

        app = create_app(
            store=store,
            embedder=embedder,
            config=config,
            project_root=project_root,
        )

        socket_path = str(guru_dir / "guru.sock")
        pid_path = guru_dir / "guru.pid"

        pid_path.write_text(str(os.getpid()))
        logger.info("Listening on %s (PID %d)", socket_path, os.getpid())

        try:
            uvicorn.run(
                app,
                uds=socket_path,
                log_config=_uvicorn_log_config(LOG_FORMAT, DATE_FORMAT),
            )
        finally:
            pid_path.unlink(missing_ok=True)
            Path(socket_path).unlink(missing_ok=True)
            logger.info("Server shut down")
    finally:
        stop_ollama_serve(ollama_proc)
