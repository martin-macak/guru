"""Content-addressed embedding cache backed by SQLite.

Keyed on (sha256(chunk_text), model_name). Stores one vector per key.
Shared across all guru projects on the machine — content identity is
the entire identity, so worktrees and unrelated projects transparently
reuse embeddings for identical chunks.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

CacheKey = tuple[bytes, str]  # (sha256_digest_32_bytes, model_name)


@dataclass
class CacheStats:
    path: str
    total_entries: int
    total_bytes: int
    by_model: dict[str, int] = field(default_factory=dict)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    content_hash   BLOB    NOT NULL,
    model          TEXT    NOT NULL,
    dimensions     INTEGER NOT NULL,
    vector         BLOB    NOT NULL,
    created_at     INTEGER NOT NULL,
    accessed_at    INTEGER NOT NULL,
    PRIMARY KEY (content_hash, model)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model);
"""


class EmbeddingCache:
    """SQLite-backed content-addressed embedding cache."""

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path), isolation_level=None, check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def get_many(self, keys: list[CacheKey], expected_dim: int) -> list[np.ndarray | None]:
        """Return vectors for each key in input order. Missing or dimension-mismatched
        entries become None. Touches accessed_at for every hit."""
        if not keys:
            return []

        result: list[np.ndarray | None] = [None] * len(keys)
        by_model: dict[str, list[tuple[int, bytes]]] = {}
        for idx, (h, model) in enumerate(keys):
            by_model.setdefault(model, []).append((idx, h))

        now_ms = int(time.time() * 1000)
        for model, entries in by_model.items():
            hashes = [h for _, h in entries]
            placeholders = ",".join("?" * len(hashes))
            rows = self._conn.execute(
                f"SELECT content_hash, dimensions, vector "
                f"FROM embeddings WHERE model = ? AND content_hash IN ({placeholders})",
                (model, *hashes),
            ).fetchall()
            by_hash = {row[0]: (row[1], row[2]) for row in rows}

            touched_hashes: list[bytes] = []
            for idx, h in entries:
                row = by_hash.get(h)
                if row is None:
                    continue
                stored_dim, blob = row
                if stored_dim != expected_dim:
                    continue
                result[idx] = np.frombuffer(blob, dtype=np.float32).copy()
                touched_hashes.append(h)

            if touched_hashes:
                placeholders_t = ",".join("?" * len(touched_hashes))
                self._conn.execute(
                    f"UPDATE embeddings SET accessed_at = ? "
                    f"WHERE model = ? AND content_hash IN ({placeholders_t})",
                    (now_ms, model, *touched_hashes),
                )
        return result

    def put_many(self, entries: list[tuple[CacheKey, np.ndarray]]) -> None:
        """Insert or replace vectors for the given keys."""
        if not entries:
            return

        now_ms = int(time.time() * 1000)
        rows = []
        for (content_hash, model), vec in entries:
            vec32 = np.asarray(vec, dtype=np.float32)
            rows.append(
                (
                    content_hash,
                    model,
                    int(vec32.shape[0]),
                    vec32.tobytes(),
                    now_ms,
                    now_ms,
                )
            )
        self._conn.executemany(
            "INSERT OR REPLACE INTO embeddings "
            "(content_hash, model, dimensions, vector, created_at, accessed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

    def stats(self) -> CacheStats:
        total_entries = self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        total_bytes = self._db_path.stat().st_size if self._db_path.exists() else 0
        wal_path = self._db_path.with_suffix(self._db_path.suffix + "-wal")
        if wal_path.exists():
            total_bytes += wal_path.stat().st_size

        by_model = {
            row[0]: row[1]
            for row in self._conn.execute(
                "SELECT model, COUNT(*) FROM embeddings GROUP BY model"
            ).fetchall()
        }
        return CacheStats(
            path=str(self._db_path),
            total_entries=total_entries,
            total_bytes=total_bytes,
            by_model=by_model,
        )

    def clear(self, model: str | None = None) -> int:
        if model is None:
            cur = self._conn.execute("DELETE FROM embeddings")
        else:
            cur = self._conn.execute("DELETE FROM embeddings WHERE model = ?", (model,))
        return cur.rowcount

    def prune(self, older_than_ms: int) -> int:
        cutoff_ms = int(time.time() * 1000) - older_than_ms
        cur = self._conn.execute("DELETE FROM embeddings WHERE accessed_at < ?", (cutoff_ms,))
        return cur.rowcount
