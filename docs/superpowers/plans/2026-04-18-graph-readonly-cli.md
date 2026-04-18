# Graph Read-Only CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four read-only subcommands to the existing `guru graph` click group (`kbs`, `kb`, `links`, `query`) — thin wrappers over the already-tested `GraphClient`, with human table output by default and `--json` opt-in.

**Architecture:** Extend the existing file `packages/guru-cli/src/guru_cli/commands/graph.py` (currently holds `start`/`stop`/`status`). Add private helpers at module scope for (a) rendering text/JSON output, (b) constructing a `GraphClient` and translating errors into click exit codes. No changes to daemon, types, `GraphClient`, HTTP API.

**Tech Stack:** Python 3.13, click, pydantic, pytest, `click.testing.CliRunner`, `unittest.mock.AsyncMock`.

**Spec:** `docs/superpowers/specs/2026-04-18-graph-readonly-cli-design.md`

---

## File Structure

### Modified files

| File | What changes |
|------|--------------|
| `packages/guru-cli/src/guru_cli/commands/graph.py` | Add four click commands (`kbs`, `kb`, `links`, `query`) plus private helpers (`_client`, `_handle_graph_errors`, `_render_kbs_table`, `_render_kb_kv`, `_render_links_table`, `_render_query_result`). |

### New files

| File | Responsibility |
|------|---------------|
| `packages/guru-cli/tests/test_graph_cli_reads.py` | Unit tests for the four new read commands using `CliRunner` + mocked `GraphClient`. |
| `packages/guru-cli/tests/test_graph_cli_safety.py` | Invariant tests: no CLI command calls a mutation method; `query` always sends `read_only=True`. |

---

## Task 1: Text rendering helpers for KB / link rows

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Create: `packages/guru-cli/tests/test_graph_cli_reads.py`

Render functions take a list of Pydantic models (or a single model / `QueryResult`) and return a string. They are pure — no I/O, no click context, no stdin.

- [ ] **Step 1: Write failing tests for the renderer helpers**

Create `packages/guru-cli/tests/test_graph_cli_reads.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from guru_core.graph_types import KbLink, KbNode, LinkKind, QueryResult
from guru_cli.commands.graph import (
    _render_kb_kv,
    _render_kbs_table,
    _render_links_table,
    _render_query_result,
)


def _kb(name: str, project_root: str = "/p", tags: list[str] | None = None,
        metadata: dict | None = None) -> KbNode:
    now = datetime(2026, 4, 18, 5, 11, 13, tzinfo=UTC)
    return KbNode(
        name=name, project_root=project_root,
        created_at=now, updated_at=now, last_seen_at=None,
        tags=tags or [], metadata=metadata or {},
    )


def _link(from_kb: str, to_kb: str, kind: LinkKind = LinkKind.DEPENDS_ON) -> KbLink:
    now = datetime(2026, 4, 18, 5, 11, 13, tzinfo=UTC)
    return KbLink(from_kb=from_kb, to_kb=to_kb, kind=kind,
                   created_at=now, metadata={})


def test_render_kbs_table_empty():
    out = _render_kbs_table([], truncate=True)
    # Header must still render even when there are zero rows, so users see
    # what columns they'd get.
    assert "NAME" in out and "PROJECT ROOT" in out
    assert out.strip().splitlines()[-1].startswith("NAME") or \
        "(no KBs)" in out


def test_render_kbs_table_single_row():
    out = _render_kbs_table([_kb("alpha", "/Users/me/alpha", tags=["app"])],
                             truncate=True)
    assert "alpha" in out
    assert "/Users/me/alpha" in out
    assert "app" in out
    assert "2026-04-18" in out


def test_render_kbs_table_renders_missing_tags_as_dash():
    out = _render_kbs_table([_kb("alpha")], truncate=True)
    # Row should have a dash where tags would be, not an empty column.
    lines = out.strip().splitlines()
    assert any("-" in line for line in lines[1:])  # skip header


def test_render_kbs_table_truncates_long_paths(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size",
                         lambda: type("S", (), {"columns": 40})())
    long_path = "/very/long/project/root/path/that/exceeds/the/terminal/width"
    out = _render_kbs_table([_kb("alpha", long_path)], truncate=True)
    assert "…" in out
    assert long_path not in out  # truncated


def test_render_kbs_table_no_truncate_flag_keeps_full_paths(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size",
                         lambda: type("S", (), {"columns": 40})())
    long_path = "/very/long/project/root/path/that/exceeds/the/terminal/width"
    out = _render_kbs_table([_kb("alpha", long_path)], truncate=False)
    assert "…" not in out
    assert long_path in out


def test_render_kb_kv_shows_all_fields():
    kb = _kb("alpha", "/p", tags=["app", "python"],
             metadata={"lang": "python", "version": "0.1"})
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
    # On that line it should show a dash, not "None".
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v`
Expected: `ImportError` — the `_render_*` helpers don't exist yet.

- [ ] **Step 3: Implement the helpers**

Modify `packages/guru-cli/src/guru_cli/commands/graph.py`. Add AFTER the existing imports, BEFORE the `@click.group` line:

```python
import json as _json
import shutil as _shutil
import sys as _sys
from datetime import datetime as _datetime
from typing import Any as _Any

from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import KbLink, KbNode, QueryResult


_ELLIPSIS = "\u2026"  # …


def _fmt_dt(d: _datetime | None) -> str:
    if d is None:
        return "-"
    return d.isoformat(timespec="seconds").replace("+00:00", "Z")


def _trunc(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    if width <= 1:
        return _ELLIPSIS
    return s[: width - 1] + _ELLIPSIS


def _term_width() -> int:
    try:
        return _shutil.get_terminal_size().columns
    except OSError:
        return 100


def _format_table(
    headers: list[str], rows: list[list[str]], *, truncate: bool
) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if len(cell) > widths[i]:
                widths[i] = len(cell)

    if truncate:
        # Reserve 2 spaces between columns. If the total is over the terminal
        # width, shrink the widest columns proportionally.
        tw = _term_width()
        separators = 2 * (len(headers) - 1)
        total = sum(widths) + separators
        if total > tw:
            # Shrink from the widest column down, leaving a floor of len(header).
            floors = [len(h) for h in headers]
            over = total - tw
            while over > 0:
                idx = widths.index(max(widths))
                if widths[idx] <= floors[idx] + 1:
                    break  # can't shrink further
                widths[idx] -= 1
                over -= 1

    def fmt_row(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            c = _trunc(cell, widths[i]) if truncate else cell
            parts.append(c.ljust(widths[i]))
        return "  ".join(parts).rstrip()

    lines = [fmt_row(headers)]
    for row in rows:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def _render_kbs_table(kbs: list[KbNode], *, truncate: bool) -> str:
    headers = ["NAME", "PROJECT ROOT", "TAGS", "UPDATED"]
    rows = [
        [
            k.name,
            k.project_root,
            ", ".join(k.tags) if k.tags else "-",
            _fmt_dt(k.updated_at),
        ]
        for k in kbs
    ]
    if not rows:
        return _format_table(headers, [], truncate=truncate) + "\n(no KBs)"
    return _format_table(headers, rows, truncate=truncate)


def _render_kb_kv(kb: KbNode) -> str:
    lines = [
        f"name:         {kb.name}",
        f"project_root: {kb.project_root}",
        f"tags:         {', '.join(kb.tags) if kb.tags else '-'}",
        f"created_at:   {_fmt_dt(kb.created_at)}",
        f"updated_at:   {_fmt_dt(kb.updated_at)}",
        f"last_seen_at: {_fmt_dt(kb.last_seen_at)}",
    ]
    if kb.metadata:
        lines.append("metadata:")
        key_w = max(len(k) for k in kb.metadata)
        for k, v in kb.metadata.items():
            lines.append(f"  {k.ljust(key_w)}  {v}")
    else:
        lines.append("metadata:     -")
    return "\n".join(lines)


def _render_links_table(links: list[KbLink], *, truncate: bool) -> str:
    headers = ["FROM", "KIND", "TO", "CREATED"]
    rows = [
        [link.from_kb, link.kind.value, link.to_kb, _fmt_dt(link.created_at)]
        for link in links
    ]
    if not rows:
        return _format_table(headers, [], truncate=truncate) + "\n(no links)"
    return _format_table(headers, rows, truncate=truncate)


def _render_query_result(r: QueryResult) -> str:
    if not r.rows:
        return f"(no rows)  elapsed: {r.elapsed_ms:.1f} ms"
    headers = list(r.columns) if r.columns else [f"col{i}" for i in range(len(r.rows[0]))]
    rows = [[_stringify(c) for c in row] for row in r.rows]
    tbl = _format_table(headers, rows, truncate=True)
    return f"{tbl}\nelapsed: {r.elapsed_ms:.1f} ms"


def _stringify(value: _Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, dict | list):
        return _json.dumps(value, default=str)
    return str(value)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/commands/graph.py \
        packages/guru-cli/tests/test_graph_cli_reads.py
git commit -m "feat(cli): add rendering helpers for graph read commands"
```

---

## Task 2: Error-handling helper — `_handle_graph_errors`

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Modify: `packages/guru-cli/tests/test_graph_cli_reads.py`

A small helper that swallows the import-missing / daemon-unreachable paths into click exit codes so each command stays ~10 lines.

- [ ] **Step 1: Add failing tests (append to existing file)**

Append to `packages/guru-cli/tests/test_graph_cli_reads.py`:

```python
import asyncio

import pytest

from guru_cli.commands.graph import _client, _handle_graph_errors


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
    # Should not raise even if no daemon is running; it only constructs the
    # client. auto_start must be False so CLI never spawns a daemon.
    try:
        c = _client()
    except SystemExit:
        pytest.skip("guru-graph not installed in this test environment")
    assert c.auto_start is False
    assert c.socket_path.endswith("graph.sock")
```

(The existing `from guru_core.graph_errors import GraphUnavailable` in the test file header must be present.  If not yet, add:)

```python
from guru_core.graph_errors import GraphUnavailable
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k "handle_graph_errors or client_returns"`
Expected: `ImportError: cannot import name '_handle_graph_errors'`.

- [ ] **Step 3: Implement helpers**

In `packages/guru-cli/src/guru_cli/commands/graph.py`, add these two helpers AFTER the render helpers, BEFORE `@click.group`:

```python
import asyncio as _asyncio


def _client():
    """Construct a GraphClient pointed at the default socket.

    Exits with code 2 if the guru-graph package isn't installed — matches the
    existing `guru graph status` behaviour.
    """
    try:
        from guru_core.graph_client import GraphClient
        from guru_graph.config import GraphPaths
    except ImportError:
        click.echo("guru-graph is not installed.", err=True)
        _sys.exit(2)
    paths = GraphPaths.default()
    return GraphClient(socket_path=str(paths.socket), auto_start=False)


def _handle_graph_errors(coro):
    """Run *coro* and translate GraphUnavailable into click's exit 1.

    Other exceptions propagate — unexpected failures should show a traceback
    so bugs are visible.
    """
    try:
        return _asyncio.run(coro)
    except GraphUnavailable as e:
        click.echo(f"daemon: unreachable ({e})", err=True)
        _sys.exit(1)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v`
Expected: all tests from Task 1 and Task 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli
git commit -m "feat(cli): add _client and _handle_graph_errors helpers"
```

---

## Task 3: `guru graph kbs` command

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Modify: `packages/guru-cli/tests/test_graph_cli_reads.py`

- [ ] **Step 1: Add failing tests (append)**

Append to `packages/guru-cli/tests/test_graph_cli_reads.py`:

```python
import json

from click.testing import CliRunner
from unittest.mock import AsyncMock, patch

from guru_cli.commands.graph import graph_group


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    """Patch GraphClient inside _client() so each test gets an AsyncMock."""
    with patch("guru_cli.commands.graph._client") as f:
        client = AsyncMock()
        f.return_value = client
        yield client


def test_kbs_list_text(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[_kb("alpha"), _kb("beta")])
    result = runner.invoke(graph_group, ["kbs"])
    assert result.exit_code == 0
    assert "alpha" in result.output and "beta" in result.output
    mock_client.list_kbs.assert_awaited_once_with(prefix=None, tag=None)


def test_kbs_list_empty(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["kbs"])
    assert result.exit_code == 0
    assert "no KBs" in result.output


def test_kbs_json(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[_kb("alpha")])
    result = runner.invoke(graph_group, ["kbs", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["name"] == "alpha"


def test_kbs_prefix_and_tag_flags(runner, mock_client):
    mock_client.list_kbs = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["kbs", "--prefix", "al", "--tag", "app"])
    assert result.exit_code == 0
    mock_client.list_kbs.assert_awaited_once_with(prefix="al", tag="app")


def test_kbs_graph_unavailable(runner, mock_client):
    mock_client.list_kbs = AsyncMock(side_effect=GraphUnavailable("boom"))
    result = runner.invoke(graph_group, ["kbs"])
    assert result.exit_code == 1
    assert "daemon: unreachable" in result.output  # click routes stderr to output
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k kbs`
Expected: click complains the `kbs` command doesn't exist ("No such command 'kbs'"). Tests FAIL.

- [ ] **Step 3: Implement `kbs` command**

In `packages/guru-cli/src/guru_cli/commands/graph.py`, add at the END of the file (after `status`):

```python
@graph_group.command(name="kbs")
@click.option("--prefix", type=str, default=None,
               help="Filter KBs whose name starts with this prefix.")
@click.option("--tag", type=str, default=None,
               help="Filter KBs that carry this tag.")
@click.option("--json", "as_json", is_flag=True, default=False,
               help="Emit JSON array instead of a text table.")
@click.option("--no-truncate", is_flag=True, default=False,
               help="Never truncate long paths; overflow the terminal width.")
def kbs(prefix: str | None, tag: str | None, as_json: bool,
         no_truncate: bool) -> None:
    """List all KB nodes in the graph."""
    client = _client()
    nodes = _handle_graph_errors(client.list_kbs(prefix=prefix, tag=tag))
    if as_json:
        click.echo(_json.dumps(
            [n.model_dump(mode="json") for n in nodes],
            indent=2, default=str,
        ))
    else:
        click.echo(_render_kbs_table(nodes, truncate=not no_truncate))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k kbs`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli
git commit -m "feat(cli): add 'guru graph kbs' command"
```

---

## Task 4: `guru graph kb <name>` command

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Modify: `packages/guru-cli/tests/test_graph_cli_reads.py`

- [ ] **Step 1: Add failing tests (append)**

Append to `packages/guru-cli/tests/test_graph_cli_reads.py`:

```python
def test_kb_show_existing_text(runner, mock_client):
    mock_client.get_kb = AsyncMock(
        return_value=_kb("alpha", tags=["app"], metadata={"lang": "python"})
    )
    result = runner.invoke(graph_group, ["kb", "alpha"])
    assert result.exit_code == 0
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
    assert result.exit_code == 0
    assert json.loads(result.output)["name"] == "alpha"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k "test_kb_show"`
Expected: "No such command 'kb'" — FAIL.

- [ ] **Step 3: Implement `kb` command**

In `packages/guru-cli/src/guru_cli/commands/graph.py`, append:

```python
@graph_group.command(name="kb")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, default=False,
               help="Emit the KbNode as JSON.")
def kb(name: str, as_json: bool) -> None:
    """Show a single KB node."""
    client = _client()
    node = _handle_graph_errors(client.get_kb(name))
    if node is None:
        click.echo(f"KB {name!r} not found", err=True)
        _sys.exit(1)
    if as_json:
        click.echo(_json.dumps(node.model_dump(mode="json"),
                                indent=2, default=str))
    else:
        click.echo(_render_kb_kv(node))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k "test_kb_show"`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli
git commit -m "feat(cli): add 'guru graph kb <name>' command"
```

---

## Task 5: `guru graph links <name>` command

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Modify: `packages/guru-cli/tests/test_graph_cli_reads.py`

- [ ] **Step 1: Add failing tests (append)**

Append to `packages/guru-cli/tests/test_graph_cli_reads.py`:

```python
def test_links_default_direction_is_both(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[_link("alpha", "beta")])
    result = runner.invoke(graph_group, ["links", "alpha"])
    assert result.exit_code == 0
    assert "alpha" in result.output and "beta" in result.output
    assert "depends_on" in result.output
    mock_client.list_links.assert_awaited_once_with(name="alpha",
                                                      direction="both")


def test_links_direction_flag(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["links", "alpha",
                                           "--direction", "out"])
    assert result.exit_code == 0
    mock_client.list_links.assert_awaited_once_with(name="alpha",
                                                      direction="out")


def test_links_empty_text(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["links", "alpha"])
    assert result.exit_code == 0
    assert "no links" in result.output


def test_links_json(runner, mock_client):
    mock_client.list_links = AsyncMock(return_value=[_link("alpha", "beta")])
    result = runner.invoke(graph_group, ["links", "alpha", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["from_kb"] == "alpha"
    assert data[0]["kind"] == "depends_on"


def test_links_invalid_direction_rejected(runner, mock_client):
    mock_client.list_links = AsyncMock()
    result = runner.invoke(graph_group, ["links", "alpha",
                                           "--direction", "sideways"])
    assert result.exit_code != 0  # click's UsageError path
    mock_client.list_links.assert_not_awaited()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k test_links`
Expected: "No such command 'links'" — FAIL.

- [ ] **Step 3: Implement `links` command**

In `packages/guru-cli/src/guru_cli/commands/graph.py`, append:

```python
@graph_group.command(name="links")
@click.argument("name")
@click.option("--direction",
               type=click.Choice(["in", "out", "both"]),
               default="both",
               help="Which direction of links to list.")
@click.option("--json", "as_json", is_flag=True, default=False,
               help="Emit JSON array instead of a text table.")
@click.option("--no-truncate", is_flag=True, default=False,
               help="Never truncate long values.")
def links(name: str, direction: str, as_json: bool, no_truncate: bool) -> None:
    """List a KB's links."""
    client = _client()
    items = _handle_graph_errors(
        client.list_links(name=name, direction=direction),
    )
    if as_json:
        click.echo(_json.dumps(
            [link.model_dump(mode="json") for link in items],
            indent=2, default=str,
        ))
    else:
        click.echo(_render_links_table(items, truncate=not no_truncate))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k test_links`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli
git commit -m "feat(cli): add 'guru graph links <name>' command"
```

---

## Task 6: `guru graph query [cypher]` command

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Modify: `packages/guru-cli/tests/test_graph_cli_reads.py`

- [ ] **Step 1: Add failing tests (append)**

Append to `packages/guru-cli/tests/test_graph_cli_reads.py`:

```python
from io import StringIO


def test_query_positional_arg(runner, mock_client):
    mock_client.query = AsyncMock(
        return_value=QueryResult(columns=["n"], rows=[[1]], elapsed_ms=0.5)
    )
    result = runner.invoke(graph_group, ["query", "MATCH (n) RETURN n"])
    assert result.exit_code == 0
    mock_client.query.assert_awaited_once()
    _, kwargs = mock_client.query.call_args
    # Safety invariant: read_only is hard-coded True.
    assert kwargs["read_only"] is True
    assert kwargs["cypher"] == "MATCH (n) RETURN n"


def test_query_read_only_cannot_be_overridden(runner, mock_client):
    """Even --help should not expose a --write flag."""
    result = runner.invoke(graph_group, ["query", "--help"])
    assert result.exit_code == 0
    assert "--write" not in result.output
    assert "read-only" in result.output.lower() or "read only" in result.output.lower()


def test_query_stdin(runner, mock_client):
    mock_client.query = AsyncMock(
        return_value=QueryResult(columns=["x"], rows=[[1]], elapsed_ms=0.1)
    )
    result = runner.invoke(graph_group, ["query"], input="RETURN 1 AS x\n")
    assert result.exit_code == 0
    _, kwargs = mock_client.query.call_args
    assert kwargs["cypher"].strip() == "RETURN 1 AS x"
    assert kwargs["read_only"] is True


def test_query_json_output(runner, mock_client):
    mock_client.query = AsyncMock(
        return_value=QueryResult(
            columns=["k.name"], rows=[["alpha"]], elapsed_ms=1.0,
        )
    )
    result = runner.invoke(graph_group, ["query", "--json", "MATCH (k) RETURN k.name"])
    assert result.exit_code == 0
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
    # CliRunner by default provides no stdin; simulate TTY via monkeypatched
    # sys.stdin.isatty. The command must not block.
    with patch("guru_cli.commands.graph._sys.stdin") as stdin:
        stdin.isatty.return_value = True
        result = runner.invoke(graph_group, ["query"])
    assert result.exit_code == 2
    assert "cypher required" in result.output.lower() or \
        "no cypher" in result.output.lower()
    mock_client.query.assert_not_awaited()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k test_query`
Expected: "No such command 'query'" — FAIL.

- [ ] **Step 3: Implement `query` command**

In `packages/guru-cli/src/guru_cli/commands/graph.py`, append:

```python
@graph_group.command(name="query")
@click.argument("cypher", required=False)
@click.option("--json", "as_json", is_flag=True, default=False,
               help="Emit the QueryResult as JSON.")
def query(cypher: str | None, as_json: bool) -> None:
    """Run a read-only Cypher query.

    The query is forced to read-only on the server — no write flag is
    exposed by the CLI regardless of the Cypher contents.

    Pass the query inline or via stdin:

        guru graph query 'MATCH (k:Kb) RETURN k.name'
        echo 'MATCH (k:Kb) RETURN count(k)' | guru graph query
        guru graph query < query.cypher
    """
    if cypher is None:
        if _sys.stdin.isatty():
            click.echo("cypher required (pass as argument or via stdin)", err=True)
            _sys.exit(2)
        cypher = _sys.stdin.read()
    client = _client()
    result = _handle_graph_errors(
        client.query(cypher=cypher, params=None, read_only=True),
    )
    if as_json:
        click.echo(_json.dumps(result.model_dump(mode="json"),
                                indent=2, default=str))
    else:
        click.echo(_render_query_result(result))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_reads.py -v -k test_query`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli
git commit -m "feat(cli): add 'guru graph query' with stdin + read-only enforcement"
```

---

## Task 7: Safety-invariant tests

**Files:**
- Create: `packages/guru-cli/tests/test_graph_cli_safety.py`

- [ ] **Step 1: Write failing-then-passing safety tests**

Create `packages/guru-cli/tests/test_graph_cli_safety.py`:

```python
"""Invariants that must hold for the CLI forever.

These tests are deliberately coarse: they inspect the click command tree
and the source file. If someone later adds a 'guru graph upsert' command,
the first test trips. If someone later flips read_only to False in any
branch of 'query', the second test trips.
"""

from __future__ import annotations

import inspect

from guru_cli.commands.graph import graph_group, query


_MUTATION_SUBCOMMANDS = {
    "upsert", "upsert-kb", "create-kb", "create",
    "delete", "delete-kb", "rm",
    "link", "create-link",
    "unlink", "delete-link",
}


def test_no_mutation_subcommands_registered():
    """The click group must expose only reads + lifecycle commands."""
    names = set(graph_group.commands.keys())
    conflicts = names & _MUTATION_SUBCOMMANDS
    assert conflicts == set(), (
        f"Mutation subcommand(s) found in 'guru graph': {conflicts}. "
        "The CLI must stay read-only per the design spec."
    )


def test_graph_group_only_contains_expected_subcommands():
    """Whitelist — accept only lifecycle + read commands."""
    allowed = {"start", "stop", "status", "kbs", "kb", "links", "query"}
    names = set(graph_group.commands.keys())
    unexpected = names - allowed
    assert unexpected == set(), (
        f"Unexpected subcommand(s) in 'guru graph': {unexpected}. "
        "Add to the whitelist only if intentional."
    )


def test_query_callback_hard_codes_read_only_true():
    """Source inspection: 'query' command must only call client.query with
    read_only=True as a literal keyword argument.
    """
    src = inspect.getsource(query)
    assert "read_only=True" in src, (
        "query must pass read_only=True literally; do not parameterise it."
    )
    assert "read_only=False" not in src
    assert "--write" not in src
```

- [ ] **Step 2: Run them**

Run: `uv run pytest packages/guru-cli/tests/test_graph_cli_safety.py -v`
Expected: 3 PASS (the implementation already satisfies the invariants).

- [ ] **Step 3: Commit**

```bash
git add packages/guru-cli/tests/test_graph_cli_safety.py
git commit -m "test(cli): add safety invariants for graph read-only CLI"
```

---

## Task 8: Final verification + smoke

**Files:** (verification only — no edits expected)

- [ ] **Step 1: Full unit suite, fast**

Run: `make test`
Expected: all pass; at least 4 new tests counted for `guru-cli`.

Note the pass/skip counts. If anything regressed, stop and fix — do NOT proceed.

- [ ] **Step 2: `guru graph --help` shows seven subcommands**

Run: `uv run guru graph --help`
Expected: output lists `kb`, `kbs`, `links`, `query`, `start`, `status`, `stop` (alphabetical — click orders them).

- [ ] **Step 3: `guru graph query --help` shows no --write flag**

Run: `uv run guru graph query --help`
Expected: help text mentions "read-only"; does NOT contain `--write`.

- [ ] **Step 4: Manual smoke (with a reachable daemon + a KB)**

If you have a daemon running (e.g. `guru graph start` plus a guru-server in a project that registered itself):

```bash
uv run guru graph kbs
uv run guru graph kbs --json
uv run guru graph kb <your-kb-name>
uv run guru graph links <your-kb-name>
uv run guru graph query 'MATCH (k:Kb) RETURN count(k) AS n'
echo 'MATCH (k:Kb) RETURN k.name LIMIT 5' | uv run guru graph query
```

If no daemon is running, the commands should each exit 1 with `daemon: unreachable` on stderr. This is expected.

- [ ] **Step 5: Commit anything that surfaced during manual smoke (rare)**

Only if step 4 reveals a fit/finish issue; otherwise nothing to commit.

---

## Self-review

**Spec coverage:**
- Four new commands (`kbs`, `kb`, `links`, `query`) → Tasks 3–6 ✅
- Human tables default, `--json` opt-in → helpers in Task 1, wired in Tasks 3–6 ✅
- `query` always `read_only=True` → Task 6 implementation + Task 7 invariant ✅
- No mutation commands exposed → Task 7 invariant ✅
- Error handling (daemon unreachable, KB not found, server 500, import missing) → Task 2 + Task 4 + Task 6 ✅
- TTY stdin + empty query → Task 6 test `test_query_no_positional_and_tty_stdin_exits_2` ✅
- Human render of missing tags / missing metadata / missing last_seen_at as dashes → Task 1 tests ✅
- Terminal-width truncation + `--no-truncate` → Task 1 tests + `_format_table` ✅
- Success criteria (help lists commands, smoke works) → Task 8 ✅

**Placeholder scan:** grep of the plan for "TBD", "TODO", "fill in", "similar to" — none present. Every code block contains real, runnable code.

**Type consistency:** `_client()`, `_handle_graph_errors(coro)`, `_render_*` helper names all match across tasks. Import order in `graph.py` is consistent (the helper block goes BEFORE `@click.group`; commands appended at end in order 3,4,5,6). No method-name drift (`list_kbs` / `get_kb` / `list_links` / `query` come from the existing `GraphClient` — spot-checked against `packages/guru-core/src/guru_core/graph_client.py`).
