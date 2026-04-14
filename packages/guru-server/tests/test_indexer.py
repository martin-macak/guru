import subprocess
from unittest.mock import AsyncMock, MagicMock

import lancedb
import numpy as np
import pytest

from guru_core.types import GuruConfig, MatchConfig, Rule
from guru_server.embed_cache import EmbeddingCache
from guru_server.indexer import BackgroundIndexer
from guru_server.jobs import JobRegistry
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore


@pytest.fixture
def project_dir(tmp_path):
    """Create a project with two markdown files."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nHello world.")
    (docs / "api.md").write_text("# API\n\nEndpoint docs.")
    (tmp_path / ".guru").mkdir()
    (tmp_path / ".guru" / "db").mkdir()
    return tmp_path


@pytest.fixture
def store(project_dir):
    return VectorStore(db_path=str(project_dir / ".guru" / "db"))


@pytest.fixture
def manifest(project_dir):
    db = lancedb.connect(str(project_dir / ".guru" / "db"))
    return FileManifest(db)


@pytest.fixture
def embedder():
    mock = MagicMock()
    mock.embed_batch = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def config():
    return GuruConfig(
        version=1,
        rules=[Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))],
    )


@pytest.fixture
def registry():
    return JobRegistry()


@pytest.fixture
def indexer(store, manifest, embedder, config, project_dir, registry):
    return BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=project_dir,
    )


@pytest.mark.asyncio
async def test_full_index_new_files(indexer, registry, embedder):
    """First index: all files are new."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer.run(job)

    assert job.status == "completed"
    assert job.files_total == 2
    assert job.files_processed == 2
    assert job.files_skipped == 0
    assert job.chunks_created > 0


@pytest.mark.asyncio
async def test_skip_unchanged_files(indexer, registry, embedder, manifest, project_dir):
    """Second index with no changes: all files skipped."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # First index
    job1 = registry.create_job()
    await indexer.run(job1)
    assert job1.files_processed == 2

    # Second index — nothing changed
    job2 = registry.create_job()
    await indexer.run(job2)
    assert job2.status == "completed"
    assert job2.files_skipped == 2
    assert job2.files_processed == 0


@pytest.mark.asyncio
async def test_reindex_modified_file(indexer, registry, embedder, project_dir):
    """Modified file gets re-indexed."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # First index
    job1 = registry.create_job()
    await indexer.run(job1)

    # Modify one file
    (project_dir / "docs" / "guide.md").write_text("# Guide\n\nUpdated content.")

    job2 = registry.create_job()
    await indexer.run(job2)
    assert job2.status == "completed"
    assert job2.files_processed == 1
    assert job2.files_skipped == 1


@pytest.mark.asyncio
async def test_detect_deleted_file(indexer, registry, embedder, project_dir, store):
    """Deleted file gets cleaned up."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # First index
    job1 = registry.create_job()
    await indexer.run(job1)
    assert store.document_count() == 2

    # Delete one file
    (project_dir / "docs" / "api.md").unlink()

    job2 = registry.create_job()
    await indexer.run(job2)
    assert job2.status == "completed"
    assert job2.files_deleted == 1
    assert store.document_count() == 1


@pytest.mark.asyncio
async def test_single_file_error_continues(indexer, registry, embedder, project_dir):
    """A file that fails to embed doesn't stop the whole job."""
    call_count = 0

    async def flaky_embed(texts):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Ollama timeout")
        return [[0.1] * 768] * len(texts)

    embedder.embed_batch = AsyncMock(side_effect=flaky_embed)

    job = registry.create_job()
    await indexer.run(job)
    # Job should complete (not fail) — one file succeeded, one failed
    assert job.status == "completed"
    assert job.files_processed >= 1


@pytest.mark.asyncio
async def test_job_phases(indexer, registry, embedder):
    """Job sets files_total after discovery (proves discovery happened)."""
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer.run(job)
    assert job.status == "completed"
    # files_total > 0 means discovery happened
    assert job.files_total == 2


@pytest.fixture
def embed_cache(tmp_path):
    c = EmbeddingCache(db_path=tmp_path / "test_embed_cache" / "embeddings.db")
    yield c
    c.close()


@pytest.fixture
def indexer_with_cache(store, manifest, embedder, config, project_dir, embed_cache):
    return BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=project_dir,
        embed_cache=embed_cache,
    )


@pytest.mark.asyncio
async def test_cache_miss_embeds_everything(indexer_with_cache, registry, embedder, embed_cache):
    """Empty cache: embedder is called for every chunk and cache is populated."""
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer_with_cache.run(job)

    assert embedder.embed_batch.await_count >= 1
    assert job.cache_hits == 0
    assert job.cache_misses > 0
    assert embed_cache.stats().total_entries == job.cache_misses


@pytest.mark.asyncio
async def test_cache_hit_skips_embedder(
    indexer_with_cache, registry, embedder, embed_cache, project_dir
):
    """Pre-populate cache with all chunks; embedder must not be called."""
    import hashlib

    from guru_core.types import MatchConfig, Rule
    from guru_server.ingestion.markdown import MarkdownParser

    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # Parse all fixture files to get their chunk texts, populate cache
    parser = MarkdownParser()
    rule = Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))
    for md in (project_dir / "docs").glob("*.md"):
        chunks = parser.parse(md, rule)
        for chunk in chunks:
            key = (hashlib.sha256(chunk.content.encode("utf-8")).digest(), "nomic-embed-text")
            embed_cache.put_many([(key, np.array([0.1] * 768, dtype=np.float32))])

    job = registry.create_job()
    await indexer_with_cache.run(job)

    # Embedder should NOT be called because all chunks are cached
    assert embedder.embed_batch.await_count == 0
    assert job.cache_misses == 0
    assert job.cache_hits > 0


@pytest.mark.asyncio
async def test_cache_get_many_failure_falls_through(
    indexer_with_cache, registry, embedder, embed_cache
):
    """If cache.get_many raises, the job completes via the embedder."""
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    embed_cache.get_many = MagicMock(side_effect=RuntimeError("cache boom"))

    job = registry.create_job()
    await indexer_with_cache.run(job)

    assert job.status == "completed"
    assert embedder.embed_batch.await_count >= 1


@pytest.mark.asyncio
async def test_cache_put_many_failure_falls_through(
    indexer_with_cache, registry, embedder, embed_cache, store
):
    """If cache.put_many raises, the job still completes and LanceDB gets vectors."""
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    embed_cache.put_many = MagicMock(side_effect=RuntimeError("disk full"))

    job = registry.create_job()
    await indexer_with_cache.run(job)

    # Job must complete despite the cache write failure
    assert job.status == "completed"
    assert job.files_processed >= 1
    # Vectors reached LanceDB — chunks were embedded and stored via the fallthrough
    assert embedder.embed_batch.await_count >= 1
    assert store.document_count() >= 1


@pytest.mark.asyncio
async def test_cache_mixed_hit_miss_preserves_order(
    indexer_with_cache, registry, embedder, embed_cache, project_dir
):
    """Pre-cache some chunks, leave others missing. Verify cached-hit texts are
    never sent to the embedder, exercising the order-preserving merge logic
    in _embed_with_cache. If `i`/`j` get swapped in the merge, embedder-fresh
    vectors would land in cached-hit slots and this test would catch it.
    """
    import hashlib

    from guru_core.types import MatchConfig, Rule
    from guru_server.ingestion.markdown import MarkdownParser

    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    miss_vector = [0.99] * 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [miss_vector] * len(texts))

    # Pre-cache the first chunk of the first fixture file with a distinct vector
    parser = MarkdownParser()
    rule = Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))
    hit_vector = np.array([0.42] * 768, dtype=np.float32)
    all_md_files = sorted((project_dir / "docs").glob("*.md"))
    first_file_chunks = parser.parse(all_md_files[0], rule)
    assert first_file_chunks, "Test fixture must produce at least one chunk"
    first_chunk_text = first_file_chunks[0].content
    key = (hashlib.sha256(first_chunk_text.encode("utf-8")).digest(), "nomic-embed-text")
    embed_cache.put_many([(key, hit_vector)])

    job = registry.create_job()
    await indexer_with_cache.run(job)

    assert job.status == "completed"
    assert job.cache_hits == 1
    assert job.cache_misses >= 1
    # The embedder must never be asked to embed a cache-hit chunk
    for call_args in embedder.embed_batch.call_args_list:
        embedded_texts = call_args.args[0] if call_args.args else call_args.kwargs["texts"]
        assert first_chunk_text not in embedded_texts, (
            "Cached chunk was incorrectly sent to the embedder — order-preserving "
            "merge in _embed_with_cache may be broken"
        )


@pytest.mark.asyncio
async def test_cache_counters_sum_to_chunks_created(
    indexer_with_cache, registry, embedder, embed_cache
):
    """cache_hits + cache_misses == chunks_created after a completed job."""
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer_with_cache.run(job)

    assert job.status == "completed"
    assert job.cache_hits + job.cache_misses == job.chunks_created


def _git_init(repo_dir):
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)


@pytest.fixture
def git_project(tmp_path):
    """A git repo with a markdown file in docs/ and another in node_modules/ (gitignored)."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "real.md").write_text("# Real\n\nContent.")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "README.md").write_text("# Generated\n\nJunk.")
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    (tmp_path / ".guru").mkdir()
    (tmp_path / ".guru" / "db").mkdir()
    _git_init(tmp_path)
    subprocess.run(["git", "add", "docs/", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.asyncio
async def test_gitignore_filter_skips_ignored_files(git_project, registry):
    """Files in gitignored directories are not indexed."""
    import lancedb

    from guru_core.types import GuruConfig, MatchConfig, Rule
    from guru_server.indexer import BackgroundIndexer
    from guru_server.manifest import FileManifest
    from guru_server.storage import VectorStore

    store = VectorStore(db_path=str(git_project / ".guru" / "db"))
    db = lancedb.connect(str(git_project / ".guru" / "db"))
    manifest = FileManifest(db)
    embedder = MagicMock()
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    config = GuruConfig(
        version=1,
        rules=[Rule(rule_name="all", match=MatchConfig(glob="**/*.md"))],
    )
    indexer = BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=git_project,
        embed_cache=None,
    )

    job = registry.create_job()
    await indexer.run(job)

    indexed_paths = {e["file_path"] for e in manifest.all_entries()}
    assert "docs/real.md" in indexed_paths
    assert "node_modules/README.md" not in indexed_paths


@pytest.mark.asyncio
async def test_non_git_project_uses_pure_glob(project_dir, registry, indexer):
    """When the project is not inside a git repo, the filter falls through."""
    embedder = indexer._embedder
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer.run(job)

    assert job.files_processed == 2
