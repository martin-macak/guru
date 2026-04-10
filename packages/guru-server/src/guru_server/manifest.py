from __future__ import annotations

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


def _escape(value: str) -> str:
    return value.replace("'", "''")
