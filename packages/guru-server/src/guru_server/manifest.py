from __future__ import annotations

import contextlib
import logging
import time

import lancedb

logger = logging.getLogger(__name__)

TABLE_NAME = "file_manifest"

_TABLE_NOT_FOUND_PHRASES = ("not found", "does not exist", "no such", "notfounderror")


class FileManifest:
    """Tracks per-file indexing state in a LanceDB table."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        self._db = db
        self._table = None

    def _get_table(self):
        if self._table is None:
            try:
                self._table = self._db.open_table(TABLE_NAME)
            except FileNotFoundError:
                return None
            except Exception as exc:
                msg = str(exc).lower()
                if any(phrase in msg for phrase in _TABLE_NOT_FOUND_PHRASES):
                    return None
                raise

            # Validate table integrity — a corrupted table (e.g. missing data
            # files after a failed indexing run) would fail on any read.
            # count_rows() reads from metadata and succeeds even when data
            # files are missing, so we only probe with head() when rows exist.
            try:
                if self._table.count_rows() > 0:
                    self._table.head(1).to_pydict()
            except Exception as exc:
                logger.warning(
                    "Table '%s' is corrupted and will be dropped: %s",
                    TABLE_NAME,
                    exc,
                )
                try:
                    self._db.drop_table(TABLE_NAME)
                except Exception:
                    logger.warning(
                        "Failed to drop corrupted table '%s'; ignoring",
                        TABLE_NAME,
                    )
                self._table = None
                return None
        return self._table

    def _ensure_table(self):
        table = self._get_table()
        if table is None:
            self._table = self._db.create_table(
                TABLE_NAME,
                data=[
                    {
                        "file_path": "__placeholder__",
                        "content_hash": "",
                        "mtime": 0.0,
                        "indexed_at": 0.0,
                        "chunk_count": 0,
                    }
                ],
            )
            self._table.delete("file_path = '__placeholder__'")
        return self._table

    def get_entry(self, file_path: str) -> dict | None:
        table = self._get_table()
        if table is None:
            return None
        rows = (
            table.search(None)
            .where(f"file_path = '{_escape(file_path)}'", prefilter=True)
            .select(["file_path", "content_hash", "mtime", "indexed_at", "chunk_count"])
            .to_list()
        )
        if not rows:
            return None
        return rows[0]

    def all_entries(self) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        return (
            table.search(None)
            .select(["file_path", "content_hash", "mtime", "indexed_at", "chunk_count"])
            .to_list()
        )

    def upsert(self, file_path: str, *, content_hash: str, mtime: float, chunk_count: int) -> None:
        table = self._ensure_table()
        # Delete existing entry if present
        table.delete(f"file_path = '{_escape(file_path)}'")
        table.add(
            [
                {
                    "file_path": file_path,
                    "content_hash": content_hash,
                    "mtime": mtime,
                    "indexed_at": time.time(),
                    "chunk_count": chunk_count,
                }
            ]
        )

    def update_mtime(self, file_path: str, *, mtime: float) -> None:
        entry = self.get_entry(file_path)
        if entry is None:
            return
        table = self._get_table()
        table.delete(f"file_path = '{_escape(file_path)}'")
        table.add(
            [
                {
                    "file_path": file_path,
                    "content_hash": entry["content_hash"],
                    "mtime": mtime,
                    "indexed_at": entry["indexed_at"],
                    "chunk_count": entry["chunk_count"],
                }
            ]
        )

    def delete_entry(self, file_path: str) -> None:
        table = self._get_table()
        if table is None:
            return
        table.delete(f"file_path = '{_escape(file_path)}'")

    def delete_entries(self, file_paths: list[str]) -> None:
        table = self._get_table()
        if table is None:
            return
        escaped = ", ".join(f"'{_escape(fp)}'" for fp in file_paths)
        table.delete(f"file_path IN ({escaped})")

    def reset(self) -> None:
        """Drop the manifest table entirely to force a full re-index."""
        with contextlib.suppress(Exception):
            self._db.drop_table(TABLE_NAME)
        self._table = None


def _escape(value: str) -> str:
    return value.replace("'", "''")
