from __future__ import annotations

import pytest

pytestmark = pytest.mark.real_neo4j


def test_backend_starts_and_reports_version(real_neo4j_backend):
    h = real_neo4j_backend.health()
    assert h.healthy is True
    info = real_neo4j_backend.info()
    assert info.name == "neo4j"
    assert info.version != "unknown"


def test_execute_returns_rows(real_neo4j_backend):
    res = real_neo4j_backend.execute_read("RETURN 1 AS x", {})
    assert res.rows == [[1]]
    assert res.columns == ["x"]


def test_upsert_and_get_kb(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    real_neo4j_backend.upsert_kb(name="alpha", project_root="/a", tags=[], metadata_json="{}")
    row = real_neo4j_backend.get_kb("alpha")
    assert row is not None
    assert row["name"] == "alpha"


def test_link_and_list_links(real_neo4j_backend):
    real_neo4j_backend.ensure_schema(target_version=1)
    real_neo4j_backend.upsert_kb(name="a", project_root="/a", tags=[], metadata_json="{}")
    real_neo4j_backend.upsert_kb(name="b", project_root="/b", tags=[], metadata_json="{}")
    real_neo4j_backend.link(from_kb="a", to_kb="b", kind="depends_on", metadata_json="{}")
    outs = real_neo4j_backend.list_links_for(name="a", direction="out")
    assert len(outs) == 1
    assert outs[0]["kind"] == "depends_on"
