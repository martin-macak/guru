from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI

from guru_core.types import GuruConfig
from guru_server.api import api_router
from guru_server.embed_cache import EmbeddingCache
from guru_server.embedding import OllamaEmbedder
from guru_server.graph_integration import build_graph_client_if_enabled, register_self_kb
from guru_server.indexer import BackgroundIndexer
from guru_server.jobs import JobRegistry
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle: auto-index on startup, file watcher."""
    watcher_task = None

    # Keep a set of background tasks alive to prevent GC
    _background_tasks: set[asyncio.Task] = set()

    # Register this server's KB node in the graph (silent degrade on failure).
    try:
        await register_self_kb(
            client=app.state.graph_client,
            name=app.state.project_name,
            project_root=str(app.state.project_root),
        )
    except Exception:
        logger.exception("register_self_kb raised unexpectedly — continuing")

    if app.state.indexer is not None:
        # Auto-index on startup
        job = app.state.job_registry.create_job()
        logger.info("Auto-indexing on startup (job %s)", job.job_id[:8])

        async def _run_startup_index():
            nonlocal watcher_task
            try:
                await app.state.indexer.run(job)
            except Exception:
                logger.exception("Startup indexing failed for job %s", job.job_id[:8])
                return

            if job.status != "completed":
                logger.warning(
                    "Startup indexing did not complete for job %s (status=%s)",
                    job.job_id[:8],
                    job.status,
                )
                return

            from datetime import UTC, datetime

            app.state.last_indexed = datetime.now(UTC)

            # Start file watcher after initial index completes
            try:
                from guru_server.watcher import start_watcher

                async def _submit_index():
                    new_job = app.state.job_registry.create_job()

                    async def _run_watcher_index():
                        try:
                            await app.state.indexer.run(new_job)
                        except Exception:
                            logger.exception(
                                "Watcher-triggered indexing failed for job %s",
                                new_job.job_id[:8],
                            )
                            return
                        if new_job.status == "completed":
                            from datetime import UTC, datetime

                            app.state.last_indexed = datetime.now(UTC)

                    t = asyncio.create_task(_run_watcher_index())
                    _background_tasks.add(t)
                    t.add_done_callback(_background_tasks.discard)

                watcher_task = asyncio.create_task(
                    start_watcher(
                        project_root=Path(app.state.project_root),
                        config=app.state.config,
                        job_registry=app.state.job_registry,
                        submit_index=_submit_index,
                    )
                )
            except Exception:
                logger.exception("Failed to start file watcher")

        startup_task = asyncio.create_task(_run_startup_index())
        _background_tasks.add(startup_task)
        startup_task.add_done_callback(_background_tasks.discard)

    yield

    # Cleanup: stop watcher
    if watcher_task is not None:
        watcher_task.cancel()
        with suppress(asyncio.CancelledError):
            await watcher_task


def create_app(
    store: VectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    config: GuruConfig | None = None,
    project_root: str | None = None,
    auto_index: bool = True,
    embed_cache: EmbeddingCache | None = None,
    project_name: str | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Accepts optional overrides for testing. In production these are
    created from the server's startup sequence.

    Args:
        auto_index: If True (default), auto-index on startup and start
            the file watcher. Set to False in tests that don't need it.
    """
    app = FastAPI(
        title="Guru Server",
        version="0.1.0",
        lifespan=lifespan if auto_index else None,
    )
    app.state.store = store
    app.state.embedder = embedder
    app.state.config = config if config is not None else GuruConfig()
    app.state.project_root = project_root or "."
    app.state.last_indexed = None
    app.state.job_registry = JobRegistry()
    app.state.embed_cache = embed_cache

    # Create manifest using the same LanceDB connection as the store
    if store is not None and hasattr(store, "db"):
        app.state.manifest = FileManifest(store.db)
    else:
        app.state.manifest = None

    app.state.project_name = (
        project_name or app.state.config.name or Path(app.state.project_root).name
    )

    # Create indexer if we have all dependencies
    if store is not None and embedder is not None and app.state.manifest is not None:
        app.state.indexer = BackgroundIndexer(
            store=store,
            manifest=app.state.manifest,
            embedder=embedder,
            config=app.state.config,
            project_root=Path(app.state.project_root),
            kb_name=app.state.project_name,
            embed_cache=embed_cache,
        )
    else:
        app.state.indexer = None

    graph_enabled = bool(app.state.config.graph and app.state.config.graph.enabled)
    app.state.graph_enabled = graph_enabled
    app.state.graph_client = build_graph_client_if_enabled(graph_enabled=graph_enabled)

    app.include_router(api_router)
    return app
