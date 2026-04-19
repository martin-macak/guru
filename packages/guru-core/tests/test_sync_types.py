from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from guru_core.graph_types import (
    DocumentSearchHit,
    FederationRootNode,
    GraphRootsPayload,
    KbNode,
    SyncStatus,
)


def test_sync_status_defaults():
    status = SyncStatus(
        lancedb_count=10,
        graph_count=10,
        drift=0,
        last_reconciled_at=None,
        graph_enabled=True,
    )
    assert status.drift == 0
    assert status.graph_enabled is True


def test_sync_status_rejects_negative_counts():
    with pytest.raises(ValidationError):
        SyncStatus(
            lancedb_count=-1,
            graph_count=0,
            drift=0,
            last_reconciled_at=None,
            graph_enabled=True,
        )


def test_document_search_hit_shape():
    hit = DocumentSearchHit(path="README.md", title="Readme", excerpt="...", score=0.87)
    assert hit.score == pytest.approx(0.87)


def test_graph_roots_payload_holds_federation_and_kbs():
    now = datetime.now(tz=UTC)
    kb = KbNode(
        name="local",
        project_root="/tmp/x",
        created_at=now,
        updated_at=now,
        last_seen_at=None,
        tags=[],
        metadata={},
    )
    payload = GraphRootsPayload(
        federation_root=FederationRootNode(id="federation", label="Federation"),
        kbs=[kb],
    )
    assert payload.federation_root.id == "federation"
    assert payload.kbs[0].name == "local"
