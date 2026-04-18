from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from guru_cli.commands.graph import (
    _client,
    _handle_graph_errors,
    _render_kb_kv,
    _render_kbs_table,
    _render_links_table,
    _render_query_result,
    graph_group,
)
from guru_core.graph_errors import GraphUnavailable
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


# ---- Task 2: _client + _handle_graph_errors ----


def test_handle_graph_errors_passes_successful_return():
    async def ok():
        return 42

    assert _handle_graph_errors(ok()) == 42


def test_handle_graph_errors_exits_1_on_graph_unavailable(capsys):
    async def boom():
        raise GraphUnavailable("socket missing: /tmp/x")

    with pytest.raises(SystemExit) as exc:
        _handle_graph_errors(boom())
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "daemon: unreachable" in err
    assert "socket missing" in err


def test_client_returns_graphclient_pointed_at_default_socket():
    try:
        c = _client()
    except SystemExit:
        pytest.skip("guru-graph not installed in this test environment")
    assert c.auto_start is False
    assert c.socket_path.endswith("graph.sock")


# ---- Task 3: guru graph kbs command ----


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    with patch("guru_cli.commands.graph._client") as f:
        client = AsyncMock()
        f.return_value = client
        yield client


def test_kbs_list_text(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[_kb("alpha"), _kb("beta")])
    result = runner.invoke(graph_group, ["kbs"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output and "beta" in result.output
    mock_client.list_kbs.assert_awaited_once_with(prefix=None, tag=None)


def test_kbs_list_empty(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["kbs"])
    assert result.exit_code == 0, result.output
    assert "no KBs" in result.output


def test_kbs_json(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[_kb("alpha")])
    result = runner.invoke(graph_group, ["kbs", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["name"] == "alpha"


def test_kbs_prefix_and_tag_flags(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["kbs", "--prefix", "al", "--tag", "app"])
    assert result.exit_code == 0, result.output
    mock_client.list_kbs.assert_awaited_once_with(prefix="al", tag="app")


def test_kbs_graph_unavailable(runner, mock_client):
    mock_client.list_kbs = AsyncMock(side_effect=GraphUnavailable("boom"))
    result = runner.invoke(graph_group, ["kbs"])
    assert result.exit_code == 1
    # click's CliRunner merges stderr into output by default
    assert "daemon: unreachable" in result.output


# ---- Task 4: guru graph kb NAME ----


def test_kb_show_existing_text(runner, mock_client):
    mock_client.get_kb = AsyncMock(
        return_value=_kb("alpha", tags=["app"], metadata={"lang": "python"})
    )
    result = runner.invoke(graph_group, ["kb", "alpha"])
    assert result.exit_code == 0, result.output
    assert "name:" in result.output and "alpha" in result.output
    assert "lang" in result.output and "python" in result.output
    mock_client.get_kb.assert_awaited_once_with("alpha")


def test_kb_show_missing_exits_1(runner, mock_client):
    mock_client.get_kb = AsyncMock(return_value=None)
    result = runner.invoke(graph_group, ["kb", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_kb_show_json(runner, mock_client):
    mock_client.get_kb = AsyncMock(return_value=_kb("alpha"))
    result = runner.invoke(graph_group, ["kb", "alpha", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["name"] == "alpha"


# ---- Task 5: guru graph links NAME ----


def test_links_default_direction_is_both(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[_link("alpha", "beta")])
    result = runner.invoke(graph_group, ["links", "alpha"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output and "beta" in result.output
    assert "depends_on" in result.output
    mock_client.list_links.assert_awaited_once_with(name="alpha", direction="both")


def test_links_direction_flag(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["links", "alpha", "--direction", "out"])
    assert result.exit_code == 0, result.output
    mock_client.list_links.assert_awaited_once_with(name="alpha", direction="out")


def test_links_empty_text(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["links", "alpha"])
    assert result.exit_code == 0, result.output
    assert "no links" in result.output


def test_links_json(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[_link("alpha", "beta")])
    result = runner.invoke(graph_group, ["links", "alpha", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data[0]["from_kb"] == "alpha"
    assert data[0]["kind"] == "depends_on"


def test_links_invalid_direction_rejected(runner, mock_client):
    mock_client.list_links = AsyncMock()
    result = runner.invoke(graph_group, ["links", "alpha", "--direction", "sideways"])
    assert result.exit_code != 0
    mock_client.list_links.assert_not_awaited()


# ---- Task 6: guru graph query ----


def test_query_positional_arg(runner, mock_client):
    mock_client.query = AsyncMock(
        return_value=QueryResult(columns=["n"], rows=[[1]], elapsed_ms=0.5)
    )
    result = runner.invoke(graph_group, ["query", "MATCH (n) RETURN n"])
    assert result.exit_code == 0, result.output
    mock_client.query.assert_awaited_once()
    _, kwargs = mock_client.query.call_args
    # Safety: read_only is hard-coded True.
    assert kwargs["read_only"] is True
    assert kwargs["cypher"] == "MATCH (n) RETURN n"


def test_query_read_only_cannot_be_overridden(runner, mock_client):
    """Help output must not expose a --write flag."""
    result = runner.invoke(graph_group, ["query", "--help"])
    assert result.exit_code == 0
    assert "--write" not in result.output
    assert "read-only" in result.output.lower() or "read only" in result.output.lower()


def test_query_stdin(runner, mock_client):
    mock_client.query = AsyncMock(
        return_value=QueryResult(columns=["x"], rows=[[1]], elapsed_ms=0.1)
    )
    result = runner.invoke(graph_group, ["query"], input="RETURN 1 AS x\n")
    assert result.exit_code == 0, result.output
    _, kwargs = mock_client.query.call_args
    assert kwargs["cypher"].strip() == "RETURN 1 AS x"
    assert kwargs["read_only"] is True


def test_query_json_output(runner, mock_client):
    mock_client.query = AsyncMock(
        return_value=QueryResult(
            columns=["k.name"],
            rows=[["alpha"]],
            elapsed_ms=1.0,
        )
    )
    result = runner.invoke(graph_group, ["query", "--json", "MATCH (k) RETURN k.name"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["columns"] == ["k.name"]
    assert data["rows"] == [["alpha"]]


def test_query_server_error_renders_detail(runner, mock_client):
    mock_client.query = AsyncMock(
        side_effect=GraphUnavailable(
            'daemon error 500: {"error":"query_failed","detail":"Invalid input","type":"CypherSyntaxError"}'
        )
    )
    result = runner.invoke(graph_group, ["query", "bogus"])
    assert result.exit_code == 1
    assert "daemon: unreachable" in result.output or "Invalid input" in result.output


def test_query_no_positional_and_tty_stdin_exits_2(runner, mock_client):
    mock_client.query = AsyncMock()
    # Simulate TTY stdin. CliRunner normally redirects stdin, so we patch the
    # graph module's sys.stdin directly.
    with patch("guru_cli.commands.graph.sys.stdin") as stdin:
        stdin.isatty.return_value = True
        result = runner.invoke(graph_group, ["query"])
    assert result.exit_code == 2
    assert "cypher required" in result.output.lower() or "no cypher" in result.output.lower()
    mock_client.query.assert_not_awaited()
