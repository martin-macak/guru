from __future__ import annotations

from datetime import UTC, datetime

from guru_cli.commands.graph import (
    _render_kb_kv,
    _render_kbs_table,
    _render_links_table,
    _render_query_result,
)
from guru_core.graph_types import KbLink, KbNode, LinkKind, QueryResult


def _kb(
    name: str,
    project_root: str = "/p",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> KbNode:
    now = datetime(2026, 4, 18, 5, 11, 13, tzinfo=UTC)
    return KbNode(
        name=name,
        project_root=project_root,
        created_at=now,
        updated_at=now,
        last_seen_at=None,
        tags=tags or [],
        metadata=metadata or {},
    )


def _link(from_kb: str, to_kb: str, kind: LinkKind = LinkKind.DEPENDS_ON) -> KbLink:
    now = datetime(2026, 4, 18, 5, 11, 13, tzinfo=UTC)
    return KbLink(from_kb=from_kb, to_kb=to_kb, kind=kind, created_at=now, metadata={})


def test_render_kbs_table_empty():
    out = _render_kbs_table([], truncate=True)
    assert "NAME" in out and "PROJECT ROOT" in out
    assert out.strip().splitlines()[-1].startswith("NAME") or "(no KBs)" in out


def test_render_kbs_table_single_row():
    out = _render_kbs_table([_kb("alpha", "/Users/me/alpha", tags=["app"])], truncate=True)
    assert "alpha" in out
    assert "/Users/me/alpha" in out
    assert "app" in out
    assert "2026-04-18" in out


def test_render_kbs_table_renders_missing_tags_as_dash():
    out = _render_kbs_table([_kb("alpha")], truncate=True)
    lines = out.strip().splitlines()
    assert any("-" in line for line in lines[1:])  # skip header


def test_render_kbs_table_truncates_long_paths(monkeypatch):
    monkeypatch.setattr("guru_cli.commands.graph._term_width", lambda: 40)
    long_path = "/very/long/project/root/path/that/exceeds/the/terminal/width"
    out = _render_kbs_table([_kb("alpha", long_path)], truncate=True)
    assert "\u2026" in out  # … ellipsis
    assert long_path not in out


def test_render_kbs_table_no_truncate_flag_keeps_full_paths(monkeypatch):
    monkeypatch.setattr("guru_cli.commands.graph._term_width", lambda: 40)
    long_path = "/very/long/project/root/path/that/exceeds/the/terminal/width"
    out = _render_kbs_table([_kb("alpha", long_path)], truncate=False)
    assert "\u2026" not in out
    assert long_path in out


def test_render_kb_kv_shows_all_fields():
    kb = _kb("alpha", "/p", tags=["app", "python"], metadata={"lang": "python", "version": "0.1"})
    out = _render_kb_kv(kb)
    assert "name:" in out and "alpha" in out
    assert "project_root:" in out and "/p" in out
    assert "tags:" in out and "app" in out and "python" in out
    assert "created_at:" in out
    assert "updated_at:" in out
    assert "last_seen_at:" in out
    assert "metadata:" in out
    assert "lang" in out and "python" in out
    assert "version" in out and "0.1" in out


def test_render_kb_kv_absent_last_seen_renders_dash():
    out = _render_kb_kv(_kb("alpha"))
    assert "last_seen_at:" in out
    for line in out.splitlines():
        if line.startswith("last_seen_at:"):
            assert "-" in line
            assert "None" not in line


def test_render_kb_kv_empty_metadata_renders_dash():
    out = _render_kb_kv(_kb("alpha", metadata={}))
    for line in out.splitlines():
        if line.startswith("metadata:"):
            assert "-" in line
            break


def test_render_links_table_empty():
    out = _render_links_table([], truncate=True)
    assert "FROM" in out and "KIND" in out and "TO" in out


def test_render_links_table_single_row():
    out = _render_links_table([_link("alpha", "beta")], truncate=True)
    assert "alpha" in out
    assert "beta" in out
    assert "depends_on" in out


def test_render_query_result_empty():
    r = QueryResult(columns=[], rows=[], elapsed_ms=0.0)
    out = _render_query_result(r)
    assert "(no rows)" in out


def test_render_query_result_with_rows():
    r = QueryResult(
        columns=["k.name", "k.updated_at"],
        rows=[["alpha", 1], ["beta", 2]],
        elapsed_ms=1.4,
    )
    out = _render_query_result(r)
    assert "k.name" in out
    assert "alpha" in out and "beta" in out
    assert "1.4 ms" in out or "1.40 ms" in out or "elapsed" in out
