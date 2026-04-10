from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from guru_core.types import Rule
from guru_server.ingestion.markdown import MarkdownParser
from guru_server.jobs import Job
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


class BackgroundIndexer:
    def __init__(
        self,
        *,
        store: VectorStore,
        manifest: FileManifest,
        embedder,
        config: list[Rule],
        project_root: Path,
    ) -> None:
        self._store = store
        self._manifest = manifest
        self._embedder = embedder
        self._config = config
        self._project_root = Path(project_root).resolve()
        self._parser = MarkdownParser()

    async def run(self, job: Job) -> None:
        """Execute a two-phase indexing job."""
        job.status = "running"
        job.started_at = datetime.now(UTC)
        short_id = job.job_id[:8]

        try:
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
        except Exception as exc:
            job.status = "failed"
            job.phase = None
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            logger.exception("[job %s] Job failed: %s", short_id, exc)

    def _discover(self, job: Job):
        """Scan files and compare against manifest. Returns (to_index, to_skip, to_delete)."""
        # Collect excluded files
        excluded_files: set[Path] = set()
        for rule in self._config:
            if rule.exclude:
                excluded_files.update(self._project_root.glob(rule.match.glob))

        # Collect all matched files with their rules
        seen_files: set[Path] = set()
        matched: list[tuple[Path, str, Rule]] = []
        for rule in self._config:
            if rule.exclude:
                continue
            for file_path in self._project_root.glob(rule.match.glob):
                if not file_path.is_file():
                    continue
                if file_path in excluded_files:
                    continue
                if file_path in seen_files:
                    continue
                if self._parser.supports(file_path):
                    seen_files.add(file_path)
                    rel_path = str(file_path.relative_to(self._project_root))
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
        """Parse, embed, and store a single file."""
        # Capture hash and mtime before parsing (avoids double read)
        content_hash = _file_hash(file_path)
        current_mtime = file_path.stat().st_mtime

        chunks = self._parser.parse(file_path, rule)
        for chunk in chunks:
            chunk.file_path = rel_path

        if not chunks:
            # Remove any stale chunks from a previous index run
            self._store.delete_file(rel_path)
            # Update manifest so change detection stays accurate for empty files
            self._manifest.upsert(
                rel_path,
                content_hash=content_hash,
                mtime=current_mtime,
                chunk_count=0,
            )
            job.files_processed += 1
            return

        texts = [chunk.content for chunk in chunks]
        vectors = await self._embedder.embed_batch(texts)

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
        logger.info("[job %s] Indexed %s (%d chunks)", short_id, rel_path, len(chunks))
