from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from guru_server.api import api_router
from guru_server.api.web import router as web_router
from guru_server.config import GuruConfig, resolve_web_config
from guru_server.embed_cache import EmbeddingCache
from guru_server.embedding import OllamaEmbedder
from guru_server.graph_integration import build_graph_client_if_enabled, register_self_kb
from guru_server.indexer import BackgroundIndexer
from guru_server.ingestion.markdown import MarkdownParser
from guru_server.ingestion.openapi import OpenApiParser
from guru_server.ingestion.python import PythonParser
from guru_server.ingestion.registry import ParserRegistry
from guru_server.jobs import JobRegistry
from guru_server.manifest import FileManifest
from guru_server.startup import run_startup_reconcile
from guru_server.storage import VectorStore
from guru_server.sync import GraphSyncAdapter, LanceDocumentAdapter, SyncService
from guru_server.web_runtime import build_web_runtime, resolve_web_assets_dir

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

    # Best-effort reconcile: ensure LanceDB ↔ graph are in sync on boot.
    try:
        run_startup_reconcile(app.state.sync)
    except Exception:
        logger.exception("startup reconcile raised unexpectedly — continuing")

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


def _detect_package_roots(project_root: Path) -> list[Path]:
    """Find Python package roots inside the project.

    A "package root" is the parent directory of a top-level package — i.e. the
    directory from which importable dotted-paths begin. Walk the project tree
    looking for directories that contain ``__init__.py``, then trace upward
    until the ancestor no longer has ``__init__.py`` (or we hit project_root);
    that ancestor's parent is the root.

    Skips ``.git``, ``.venv``, ``.guru``, ``node_modules``, ``__pycache__``,
    and similar noisy directories so a large repo doesn't make startup hang.
    """
    _SKIP = {
        ".git",
        ".venv",
        ".guru",
        ".agents",
        ".claude",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
    roots: set[Path] = set()
    project_root = project_root.resolve()
    if not project_root.exists():
        return []
    for init_file in project_root.rglob("__init__.py"):
        if any(part in _SKIP for part in init_file.relative_to(project_root).parts):
            continue
        # Walk up until the ancestor has no __init__.py.
        top = init_file.parent
        while (top.parent / "__init__.py").exists() and top.parent != project_root:
            top = top.parent
        candidate = top.parent
        roots.add(candidate)
    # Fallback: only include project_root when no package roots were detected
    # so bare-module projects (no __init__.py anywhere) still resolve to a
    # sensible qualname. When a real package root exists, project_root would
    # only confuse the parser (e.g. "src/pkg/auth.py" → "src.pkg.auth" instead
    # of "pkg.auth"), so don't add it.
    if not roots:
        roots.add(project_root)
    # Sort by depth descending — most specific root wins when the parser
    # iterates in `_derive_module_qualname`.
    return sorted(roots, key=lambda p: (-len(p.parts), str(p)))


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
    web_config = resolve_web_config(app.state.config)
    app.state.web_runtime = build_web_runtime(
        project_root=Path(app.state.project_root),
        assets_dir=resolve_web_assets_dir(Path(app.state.project_root)),
        enabled=bool(web_config.enabled),
        auto_open=bool(web_config.auto_open),
    )

    # Build parser registry — the extension point for ingestion formats.
    # Registered in priority order: Markdown for .md, Python for .py,
    # OpenApi last because its `supports()` is suffix-only (.yaml/.yml/.json)
    # and would otherwise claim any YAML/JSON file. In practice ParserRegistry
    # dispatches to the first parser that matches the file suffix; ordering
    # matters only when two parsers share a suffix, which none do today.
    parser_registry = ParserRegistry()
    parser_registry.register(MarkdownParser())
    parser_registry.register(
        PythonParser(package_roots=_detect_package_roots(Path(app.state.project_root)))
    )
    parser_registry.register(OpenApiParser())
    app.state.parser_registry = parser_registry

    graph_enabled = bool(app.state.config.graph and app.state.config.graph.enabled)
    app.state.graph_enabled = graph_enabled
    app.state.graph_client = build_graph_client_if_enabled(graph_enabled=graph_enabled)

    # Wire SyncService: keeps LanceDB document IDs mirrored to graph nodes.
    app.state.sync = SyncService(
        kb=app.state.project_name,
        lance=LanceDocumentAdapter(store=store),
        graph=GraphSyncAdapter(client=app.state.graph_client),
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
            parser_registry=parser_registry,
            graph_client=app.state.graph_client,
        )
    else:
        app.state.indexer = None

    app.include_router(api_router)
    app.include_router(web_router)
    if app.state.web_runtime.available and app.state.web_runtime.assets_dir is not None:
        app.mount(
            "/", StaticFiles(directory=app.state.web_runtime.assets_dir, html=True), name="web"
        )
    return app
