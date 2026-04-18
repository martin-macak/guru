from __future__ import annotations

import hashlib
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from guru_core.graph_client import GraphClient
from guru_core.types import GuruConfig, Rule
from guru_server.embed_cache import EmbeddingCache
from guru_server.graph_integration import graph_or_skip, parse_result_to_payload
from guru_server.ingestion.markdown import MarkdownParser
from guru_server.ingestion.registry import ParserRegistry
from guru_server.jobs import Job
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


def _default_registry() -> ParserRegistry:
    reg = ParserRegistry()
    reg.register(MarkdownParser())
    return reg


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def _git_tracked_paths(project_root: Path) -> set[str] | None:
    """Return the set of paths git considers tracked-or-unignored, relative
    to project_root. Returns None if this is not a git worktree or git is
    unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=project_root,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return set(result.stdout.decode("utf-8").split("\0")) - {""}


class BackgroundIndexer:
    def __init__(
        self,
        *,
        store: VectorStore,
        manifest: FileManifest,
        embedder,
        config: GuruConfig,
        project_root: Path,
        kb_name: str,
        embed_cache: EmbeddingCache | None = None,
        parser_registry: ParserRegistry | None = None,
        graph_client: GraphClient | None = None,
    ) -> None:
        self._store = store
        self._manifest = manifest
        self._embedder = embedder
        self._config = config
        self._project_root = Path(project_root).resolve()
        self._registry = parser_registry or _default_registry()
        self._cache = embed_cache
        self._kb_name = kb_name
        self._graph_client = graph_client

    async def run(self, job: Job) -> None:
        """Execute a two-phase indexing job."""
        job.status = "running"
        job.started_at = datetime.now(UTC)
        short_id = job.job_id[:8]

        try:
            # Consistency check: if the chunks store is empty but the manifest
            # has entries, the store was likely corrupted and rebuilt.  Clear
            # the manifest so every file is treated as new and re-indexed.
            if self._store.chunk_count() == 0:
                entries = self._manifest.all_entries()
                if entries:
                    logger.warning(
                        "[job %s] Store is empty but manifest has %d entries; "
                        "clearing manifest to force full re-index",
                        short_id,
                        len(entries),
                    )
                    self._manifest.reset()

            # Phase 1: Discovery
            job.phase = "discovery"
            to_index, to_skip, to_delete = self._discover(job)
            job.files_total = len(to_index) + len(to_skip)
            job.files_skipped = len(to_skip)

            logger.info(
                "[job %s] Discovery: %d files matched, %d unchanged, %d to index, %d deleted",
                short_id,
                job.files_total,
                job.files_skipped,
                len(to_index),
                len(to_delete),
            )

            # Phase 2: Indexing
            job.phase = "indexing"
            for file_path, rel_path, rule in to_index:
                try:
                    await self._index_file(job, file_path, rel_path, rule, short_id)
                except Exception:
                    logger.exception("[job %s] Failed to index %s", short_id, rel_path)
                    continue

            # Cleanup deleted files (batch)
            if to_delete:
                self._store.delete_files(to_delete)
                self._manifest.delete_entries(to_delete)
                job.files_deleted = len(to_delete)
                for rel_path in to_delete:
                    logger.info("[job %s] Deleted %s (removed from disk)", short_id, rel_path)
                    if self._graph_client is not None:
                        doc_id = f"{self._kb_name}::{rel_path}"
                        await graph_or_skip(
                            self._graph_client.delete_document_in_graph(
                                kb_name=self._kb_name, doc_id=doc_id
                            ),
                            feature="ingest_delete",
                        )

            job.status = "completed"
            job.phase = None
            job.finished_at = datetime.now(UTC)
            logger.info(
                "[job %s] Completed: %d files indexed, %d chunks created, %d deleted",
                short_id,
                job.files_processed,
                job.chunks_created,
                job.files_deleted,
            )
            total_chunks = job.cache_hits + job.cache_misses
            if total_chunks > 0:
                hit_rate = 100.0 * job.cache_hits / total_chunks
                logger.info(
                    "[job %s] Cache: %d/%d hits (%.1f%%), %d new embeddings",
                    short_id,
                    job.cache_hits,
                    total_chunks,
                    hit_rate,
                    job.cache_misses,
                )
        except Exception as exc:
            job.status = "failed"
            job.phase = None
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            logger.exception("[job %s] Job failed: %s", short_id, exc)

    def _discover(self, job: Job):
        """Scan files and compare against manifest. Returns (to_index, to_skip, to_delete)."""
        git_paths = _git_tracked_paths(self._project_root)

        # Collect excluded files
        excluded_files: set[Path] = set()
        for rule in self._config.rules:
            if rule.exclude:
                excluded_files.update(self._project_root.glob(rule.match.glob))

        # Collect all matched files with their rules
        seen_files: set[Path] = set()
        matched: list[tuple[Path, str, Rule]] = []
        for rule in self._config.rules:
            if rule.exclude:
                continue
            for file_path in self._project_root.glob(rule.match.glob):
                if not file_path.is_file():
                    continue
                if file_path in excluded_files:
                    continue
                if file_path in seen_files:
                    continue
                if self._registry.dispatch(file_path) is None:
                    continue
                rel_path = str(file_path.relative_to(self._project_root))
                if git_paths is not None and rel_path not in git_paths:
                    continue  # gitignored — skip
                seen_files.add(file_path)
                matched.append((file_path, rel_path, rule))

        # Check each file against manifest
        to_index: list[tuple[Path, str, Rule]] = []
        to_skip: list[str] = []
        matched_rel_paths: set[str] = set()

        for file_path, rel_path, rule in matched:
            matched_rel_paths.add(rel_path)
            entry = self._manifest.get_entry(rel_path)

            if entry is None:
                # New file
                to_index.append((file_path, rel_path, rule))
                continue

            current_mtime = file_path.stat().st_mtime
            if current_mtime == entry["mtime"]:
                # mtime unchanged — skip without hashing
                to_skip.append(rel_path)
                continue

            # mtime changed — check content hash
            current_hash = _file_hash(file_path)
            if current_hash == entry["content_hash"]:
                # Content unchanged despite mtime change (e.g. touch)
                self._manifest.update_mtime(rel_path, mtime=current_mtime)
                to_skip.append(rel_path)
                continue

            # Content changed — must re-index
            to_index.append((file_path, rel_path, rule))

        # Detect deletions: manifest entries not in matched files
        to_delete: list[str] = []
        for entry in self._manifest.all_entries():
            if entry["file_path"] not in matched_rel_paths:
                to_delete.append(entry["file_path"])

        return to_index, to_skip, to_delete

    async def _index_file(
        self, job: Job, file_path: Path, rel_path: str, rule: Rule, short_id: str
    ) -> None:
        """Parse, embed (via cache when possible), and store a single file."""
        content_hash = _file_hash(file_path)
        current_mtime = file_path.stat().st_mtime

        parser = self._registry.dispatch(file_path)
        assert parser is not None, f"no parser for {file_path} — discovery should have filtered it"
        parse_result = parser.parse(file_path, rule, kb_name=self._kb_name)
        chunks = parse_result.chunks
        # parse_result.document/nodes/edges are captured but discarded in PR-1 —
        # PR-2 wires them into graph ingestion via graph_or_skip.
        for chunk in chunks:
            chunk.file_path = rel_path

        if not chunks:
            self._store.delete_file(rel_path)
            self._manifest.upsert(
                rel_path,
                content_hash=content_hash,
                mtime=current_mtime,
                chunk_count=0,
            )
            # Treat an empty-chunks parse as a deletion for the graph — the document
            # lost all its sections; the graph should reflect that.
            if self._graph_client is not None:
                doc_id = f"{self._kb_name}::{rel_path}"
                await graph_or_skip(
                    self._graph_client.delete_document_in_graph(
                        kb_name=self._kb_name, doc_id=doc_id
                    ),
                    feature="ingest_delete",
                )
            job.files_processed += 1
            return

        texts = [chunk.content for chunk in chunks]
        vectors = await self._embed_with_cache(texts, job, short_id)

        # Replace old chunks only after new embeddings are ready so
        # parse/embed failures do not destroy the previous index.
        self._store.delete_file(rel_path)
        self._store.add_chunks(chunks, vectors)

        # Update manifest
        self._manifest.upsert(
            rel_path,
            content_hash=content_hash,
            mtime=current_mtime,
            chunk_count=len(chunks),
        )

        job.files_processed += 1
        job.chunks_created += len(chunks)
        if self._graph_client is not None:
            payload = parse_result_to_payload(parse_result)
            await graph_or_skip(
                self._graph_client.submit_parse_result(kb_name=self._kb_name, payload=payload),
                feature="ingest_artifacts",
            )
        logger.info("[job %s] Indexed %s (%d chunks)", short_id, rel_path, len(chunks))

    async def _embed_with_cache(
        self, texts: list[str], job: Job, short_id: str
    ) -> list[list[float]]:
        """Embed texts, reusing cached vectors when possible.

        Returns vectors in the same order as texts. Cache failures are
        logged and downgraded to a full embedder call.
        """
        if self._cache is None:
            new = await self._embedder.embed_batch(texts)
            job.cache_misses += len(texts)
            return new

        model_name = getattr(self._embedder, "model_name", None)
        dimensions = getattr(self._embedder, "dimensions", None)
        if model_name is None or dimensions is None:
            logger.warning(
                "[job %s] embedder lacks model_name/dimensions — bypassing cache", short_id
            )
            new = await self._embedder.embed_batch(texts)
            job.cache_misses += len(texts)
            return new

        keys: list[tuple[bytes, str]] = [
            (hashlib.sha256(t.encode("utf-8")).digest(), model_name) for t in texts
        ]

        try:
            cached = self._cache.get_many(keys, expected_dim=dimensions)
        except Exception as exc:
            logger.warning("[job %s] cache.get_many failed: %s — falling through", short_id, exc)
            cached = [None] * len(texts)

        missing_idx = [i for i, v in enumerate(cached) if v is None]
        missing_texts = [texts[i] for i in missing_idx]

        new_vectors_raw: list[list[float]] = (
            await self._embedder.embed_batch(missing_texts) if missing_texts else []
        )

        # Merge, preserving chunk order
        vectors: list[list[float]] = [None] * len(texts)  # type: ignore[list-item]
        for i, v in enumerate(cached):
            if v is not None:
                vectors[i] = v.tolist()
        for j, i in enumerate(missing_idx):
            vectors[i] = list(new_vectors_raw[j])

        # Populate cache with the new vectors
        if missing_idx:
            try:
                self._cache.put_many(
                    [
                        (keys[i], np.asarray(new_vectors_raw[j], dtype=np.float32))
                        for j, i in enumerate(missing_idx)
                    ]
                )
            except Exception as exc:
                logger.warning("[job %s] cache.put_many failed: %s — continuing", short_id, exc)

        job.cache_hits += len(texts) - len(missing_idx)
        job.cache_misses += len(missing_idx)

        return vectors  # type: ignore[return-value]
