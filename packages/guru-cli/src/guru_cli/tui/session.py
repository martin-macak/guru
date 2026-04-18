from __future__ import annotations

from guru_core.client import GuruClient
from guru_core.graph_client import GraphClient
from guru_core.types import SearchResultOut, StatusResponse

from .view_models import SearchHitVM, StatusSnapshotVM


class GuruSession:
    def __init__(self, *, guru_client: GuruClient, graph_client: GraphClient | None = None):
        self._guru = guru_client
        self._graph = graph_client

    async def load_status(self) -> StatusSnapshotVM:
        raw = StatusResponse.model_validate(await self._guru.status())
        return StatusSnapshotVM(
            server_running=raw.server_running,
            document_count=raw.document_count,
            chunk_count=raw.chunk_count,
            graph_enabled=raw.graph_enabled,
            graph_reachable=raw.graph_reachable,
        )

    async def run_search(self, query: str) -> list[SearchHitVM]:
        raw_hits = await self._guru.search(query)
        return [
            SearchHitVM(
                file_path=typed_hit.file_path,
                title=typed_hit.header_breadcrumb,
                snippet=typed_hit.content,
                score=typed_hit.score,
                labels=typed_hit.labels,
                artifact_qualname=typed_hit.artifact_qualname,
            )
            for raw_hit in raw_hits
            for typed_hit in [SearchResultOut.model_validate(raw_hit)]
        ]
