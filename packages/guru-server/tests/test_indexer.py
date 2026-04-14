from unittest.mock import AsyncMock, MagicMock

import lancedb
import pytest

from guru_core.types import GuruConfig, MatchConfig, Rule
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
