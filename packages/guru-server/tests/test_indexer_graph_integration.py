"""Tests for indexer <-> graph integration helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import lancedb
import pytest

from guru_core.graph_errors import GraphUnavailable
from guru_core.types import GuruConfig, MatchConfig, Rule
from guru_server.graph_integration import graph_or_skip, parse_result_to_payload
from guru_server.indexer import BackgroundIndexer
from guru_server.ingestion.base import GraphEdge, GraphNode, ParseResult
from guru_server.jobs import JobRegistry
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore


@pytest.fixture
def project_dir(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nHello world.")
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
    mock.embed_batch = AsyncMock(return_value=[[0.1] * 768])
    return mock


def test_parse_result_to_payload_roundtrip_document_only():
    doc = GraphNode(
        node_id="kb::x.md",
        label="Document",
        properties={"language": "markdown", "kb_name": "kb"},
    )
    pr = ParseResult(chunks=[], document=doc, nodes=[], edges=[])
    payload = parse_result_to_payload(pr)
    assert payload.chunks_count == 0
    assert payload.document.node_id == "kb::x.md"
    assert payload.document.label == "Document"


def test_parse_result_to_payload_preserves_relates_kind():
    doc = GraphNode(node_id="kb::x.md", label="Document", properties={})
    edge = GraphEdge(
        from_id="kb::x.md",
        to_id="kb::other",
        rel_type="RELATES",
        kind="references",
        properties={"snippet": "see other"},
    )
    payload = parse_result_to_payload(ParseResult(chunks=[], document=doc, nodes=[], edges=[edge]))
    assert payload.edges[0].kind == "references"
    assert payload.edges[0].properties == {"snippet": "see other"}


@pytest.mark.asyncio
async def test_graph_or_skip_swallows_graph_unavailable():
    async def _boom():
        raise GraphUnavailable("simulated")

    result = await graph_or_skip(_boom(), feature="test_2_7")
    assert result is None


@pytest.mark.asyncio
async def test_indexer_submits_parse_result_to_graph_client(
    store, manifest, embedder, project_dir
):
    config = GuruConfig(
        version=1,
        rules=[Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))],
    )
    graph_client = AsyncMock()
    indexer = BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=project_dir,
        kb_name="test",
        graph_client=graph_client,
    )

    await indexer.run(JobRegistry().create_job())

    graph_client.submit_parse_result.assert_awaited()


@pytest.mark.asyncio
async def test_indexer_deletes_document_in_graph_when_file_removed(
    store, manifest, embedder, project_dir
):
    config = GuruConfig(
        version=1,
        rules=[Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))],
    )
    graph_client = AsyncMock()
    indexer = BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=project_dir,
        kb_name="test",
        graph_client=graph_client,
    )

    await indexer.run(JobRegistry().create_job())
    (project_dir / "docs" / "guide.md").unlink()
    await indexer.run(JobRegistry().create_job())

    graph_client.delete_document_in_graph.assert_awaited_once_with(
        kb_name="test",
        doc_id="test::docs/guide.md",
    )
