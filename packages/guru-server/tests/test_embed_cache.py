from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import pytest

from guru_server.embed_cache import CacheKey, EmbeddingCache


def _key(text: str, model: str = "nomic-embed-text") -> CacheKey:
    return (hashlib.sha256(text.encode("utf-8")).digest(), model)


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    c = EmbeddingCache(db_path=tmp_path / "embeddings.db")
    yield c
    c.close()


def test_round_trip_preserves_vector(cache: EmbeddingCache):
    key = _key("hello")
    vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    cache.put_many([(key, vector)])
    result = cache.get_many([key], expected_dim=3)
    assert result[0] is not None
    np.testing.assert_array_equal(result[0], vector)


def test_miss_returns_none(cache: EmbeddingCache):
    result = cache.get_many([_key("nothing here")], expected_dim=3)
    assert result == [None]


def test_dimension_mismatch_treated_as_miss(cache: EmbeddingCache):
    key = _key("hello")
    vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    cache.put_many([(key, vector)])
    result = cache.get_many([key], expected_dim=768)
    assert result == [None]


def test_get_many_preserves_order(cache: EmbeddingCache):
    k1, k2, k3 = _key("a"), _key("b"), _key("c")
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v3 = np.array([3.0, 0.0], dtype=np.float32)
    cache.put_many([(k1, v1), (k3, v3)])

    result = cache.get_many([k1, k2, k3], expected_dim=2)
    assert len(result) == 3
    assert result[0] is not None
    np.testing.assert_array_equal(result[0], v1)
    assert result[1] is None
    assert result[2] is not None
    np.testing.assert_array_equal(result[2], v3)


def test_put_many_overwrites_existing(cache: EmbeddingCache):
    key = _key("hello")
    v1 = np.array([1.0], dtype=np.float32)
    v2 = np.array([2.0], dtype=np.float32)
    cache.put_many([(key, v1)])
    cache.put_many([(key, v2)])
    result = cache.get_many([key], expected_dim=1)
    np.testing.assert_array_equal(result[0], v2)


def test_clear_all(cache: EmbeddingCache):
    cache.put_many(
        [
            (_key("a"), np.array([1.0], dtype=np.float32)),
            (_key("b"), np.array([2.0], dtype=np.float32)),
        ]
    )
    deleted = cache.clear()
    assert deleted == 2
    assert cache.get_many([_key("a")], expected_dim=1) == [None]


def test_clear_scoped_to_model(cache: EmbeddingCache):
    cache.put_many(
        [
            (_key("a", model="m1"), np.array([1.0], dtype=np.float32)),
            (_key("b", model="m2"), np.array([2.0], dtype=np.float32)),
        ]
    )
    deleted = cache.clear(model="m1")
    assert deleted == 1
    assert cache.get_many([_key("a", model="m1")], expected_dim=1) == [None]
    assert cache.get_many([_key("b", model="m2")], expected_dim=1)[0] is not None


def test_prune_respects_accessed_at(cache: EmbeddingCache):
    old_key = _key("old")
    new_key = _key("new")
    cache.put_many([(old_key, np.array([1.0], dtype=np.float32))])

    cutoff_ms = 100 * 24 * 3600 * 1000
    old_ts = int(time.time() * 1000) - cutoff_ms
    cache._conn.execute(
        "UPDATE embeddings SET accessed_at = ? WHERE content_hash = ?",
        (old_ts, old_key[0]),
    )
    cache._conn.commit()

    cache.put_many([(new_key, np.array([2.0], dtype=np.float32))])

    deleted = cache.prune(older_than_ms=50 * 24 * 3600 * 1000)
    assert deleted == 1
    assert cache.get_many([old_key], expected_dim=1) == [None]
    assert cache.get_many([new_key], expected_dim=1)[0] is not None


def test_stats_returns_counts_and_bytes(cache: EmbeddingCache):
    cache.put_many(
        [
            (_key("a", model="m1"), np.array([1.0, 2.0], dtype=np.float32)),
            (_key("b", model="m1"), np.array([3.0, 4.0], dtype=np.float32)),
            (_key("c", model="m2"), np.array([5.0, 6.0], dtype=np.float32)),
        ]
    )
    stats = cache.stats()
    assert stats.total_entries == 3
    assert stats.total_bytes > 0
    assert stats.by_model == {"m1": 2, "m2": 1}
    assert stats.path.endswith("embeddings.db")


def test_wal_mode_enabled(cache: EmbeddingCache):
    row = cache._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


def test_get_many_touches_accessed_at(cache: EmbeddingCache):
    key = _key("hello")
    cache.put_many([(key, np.array([1.0], dtype=np.float32))])
    before = cache._conn.execute(
        "SELECT accessed_at FROM embeddings WHERE content_hash = ?", (key[0],)
    ).fetchone()[0]

    time.sleep(0.01)
    cache.get_many([key], expected_dim=1)

    after = cache._conn.execute(
        "SELECT accessed_at FROM embeddings WHERE content_hash = ?", (key[0],)
    ).fetchone()[0]
    assert after > before
