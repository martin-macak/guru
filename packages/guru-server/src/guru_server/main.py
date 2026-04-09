from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embedding import OllamaEmbedder
from guru_server.startup import (
    check_ollama_installed,
    check_model_available,
    start_ollama_serve,
    stop_ollama_serve,
)
from guru_server.storage import VectorStore


def main():
    project_root = os.environ.get("GURU_PROJECT_ROOT", os.getcwd())
    guru_dir = Path(project_root) / ".guru"

    if not guru_dir.is_dir():
        print(f"Error: {guru_dir} does not exist. Run `guru init` first.", file=sys.stderr)
        sys.exit(1)

    # Preflight checks
    check_ollama_installed()
    ollama_proc = start_ollama_serve()
    check_model_available("nomic-embed-text")

    # Initialize components
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

    # Write PID file
    pid_path.write_text(str(os.getpid()))

    try:
        uvicorn.run(app, uds=socket_path, log_level="info")
    finally:
        # Cleanup
        pid_path.unlink(missing_ok=True)
        Path(socket_path).unlink(missing_ok=True)
        stop_ollama_serve(ollama_proc)
