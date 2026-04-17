"""guru-graph-daemon entrypoint.

Invoked by `connect_or_spawn` or directly via the `guru-graph-daemon`
console script. Responsibilities:
  1. Run preflight (java + neo4j).
  2. Allocate a free loopback port.
  3. Start Neo4jBackend.
  4. Run migrations up to SCHEMA_VERSION.
  5. Serve the FastAPI app over UDS at GraphPaths.socket.
  6. Handle SIGTERM / SIGINT gracefully.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import sys

import uvicorn

from .app import create_app
from .backend import Neo4jBackend
from .config import GraphPaths, allocate_free_loopback_port
from .preflight import check_java_installed, check_neo4j_installed
from .versioning import SCHEMA_VERSION


def _configure_logging(log_file) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )


def main() -> int:
    paths = GraphPaths.default()
    paths.ensure_dirs()
    _configure_logging(paths.log_file)
    logger = logging.getLogger("guru_graph.main")

    # Connect-only mode: if GURU_NEO4J_BOLT_URI is set, skip preflight (we
    # don't need a local neo4j binary) and connect to the external Neo4j.
    external_uri = os.environ.get("GURU_NEO4J_BOLT_URI") or None
    if external_uri is None:
        try:
            check_java_installed()
            check_neo4j_installed()
        except RuntimeError as e:
            logger.error("preflight failed: %s", e)
            return 2

    port = allocate_free_loopback_port()
    backend = Neo4jBackend(
        data_dir=paths.data_dir,
        bolt_port=port,
        log_file=paths.data_dir / "neo4j.log",
        bolt_uri=external_uri,
    )
    backend.start()
    try:
        backend.ensure_schema(target_version=SCHEMA_VERSION)
        app = create_app(backend=backend)

        if paths.socket.exists():
            with contextlib.suppress(FileNotFoundError):
                paths.socket.unlink()

        stopping = {"flag": False}

        def _handle_sig(signum, frame):
            if stopping["flag"]:
                return
            stopping["flag"] = True
            logger.info("received signal %d, shutting down", signum)

        signal.signal(signal.SIGTERM, _handle_sig)
        signal.signal(signal.SIGINT, _handle_sig)

        config = uvicorn.Config(
            app,
            uds=str(paths.socket),
            log_level="info",
            access_log=False,
        )
        server = uvicorn.Server(config=config)
        server.run()
    finally:
        backend.stop()
        with contextlib.suppress(FileNotFoundError):
            paths.socket.unlink()
        with contextlib.suppress(FileNotFoundError):
            paths.pid_file.unlink()

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
