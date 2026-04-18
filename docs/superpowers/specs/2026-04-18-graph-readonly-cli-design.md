# Graph Plugin — Read-Only CLI Surface

**Date:** 2026-04-18
**Status:** Draft
**Follows:** `docs/superpowers/specs/2026-04-17-graph-plugin-design.md`

---

## Problem

PR #35 exposed the graph plugin's data operations only via HTTP (on the daemon's UDS) and the Python `GraphClient`. The CLI surface was limited to lifecycle commands (`guru graph start|stop|status`). A developer who wants to inspect the graph during debugging has to write a Python one-liner or `curl` against the socket — both friction-heavy and poorly discoverable.

At the same time, we deliberately do NOT want mutations to be exposable from a shell. A typo in an interactive session must not be able to delete a KB node or break invariants. Per the architecture, the Python client and HTTP endpoints remain the only mutation surfaces.

## Goals

1. Add read-only debugging commands to `guru graph` that let a developer see what's in the graph without leaving the shell.
2. Expose the full Cypher read surface as an escape hatch (backed by the existing `/query` endpoint with `read_only=true` forced).
3. Default to human-friendly text output; add `--json` for piping / scripting.
4. Safety invariant: **no mutation** reachable from the CLI.

## Non-Goals

- Not exposing `POST /kbs`, `DELETE /kbs/{name}`, `POST /kbs/{name}/links`, or `DELETE` link endpoints via CLI.
- Not exposing `read_only=false` on `/query` — no `--write` flag, no env var, no override.
- No pagination: `list_kbs` returns everything; users with tens of thousands of KBs can pipe `--json` through `jq`/`grep`.
- No `--output yaml|csv|tsv` in v1. Start with text + JSON.
- No `--since <time>` / last-seen filtering.
- No tab completion of KB names.
- No interactive REPL (`guru graph shell`).
- No changes to guru-graph daemon, guru-core types, HTTP API, or `GraphClient`.

---

## Commands

All four new leaves sit under the existing `guru graph` click group (sibling to `start`/`stop`/`status`). They wrap existing `GraphClient` methods — no new backend code.

```
guru graph kbs   [--prefix TEXT] [--tag TEXT] [--json] [--no-truncate]
guru graph kb    <name> [--json]
guru graph links <name> [--direction in|out|both] [--json] [--no-truncate]
guru graph query [<cypher>] [--json]    # stdin if no positional
```

### `guru graph kbs`

Wraps `GraphClient.list_kbs(prefix=..., tag=...)`.

- `--prefix TEXT` → `prefix` filter
- `--tag TEXT` → `tag` filter
- `--json` → JSON array of `KbNode.model_dump(mode="json")`
- `--no-truncate` → disable column-width truncation (default truncates long paths/metadata with `…`)

Text default: columns `NAME`, `PROJECT ROOT`, `TAGS`, `UPDATED`. Column widths are computed from content with a minimum for each; long strings truncate to fit inside `shutil.get_terminal_size().columns`. Absent tags render as `-`.

Exit 0 with empty table if no KBs.

### `guru graph kb <name>`

Wraps `GraphClient.get_kb(name)`.

Text default: key-value block —

```
name:         alpha
project_root: /Users/me/projects/alpha
tags:         app, python
created_at:   2026-04-17T21:05:45+00:00
updated_at:   2026-04-18T05:11:13+00:00
last_seen_at: -
metadata:
  lang:    python
  version: 0.1
```

`metadata` is pretty-printed inline. `--json` → `KbNode.model_dump(mode="json")`.

Missing KB → exit 1, stderr `KB <name> not found`.

### `guru graph links <name>`

Wraps `GraphClient.list_links(name=..., direction=...)`.

- `--direction in|out|both` (default: `both`)
- `--json`, `--no-truncate` as above

Text default columns: `FROM`, `KIND`, `TO`, `CREATED`.

Missing source KB → the backend returns `[]` (no error), matching HTTP behaviour — no special handling.

### `guru graph query [<cypher>]`

Wraps `GraphClient.query(cypher=..., read_only=True)`.

- Positional `<cypher>` if given → inline query.
- No positional → read from stdin. Supports `cypher-shell`-style heredocs and `<` redirection.
- If no positional AND stdin is a TTY (interactive shell, nothing piped in) → exit 2 with `stderr: cypher required (pass as argument or via stdin)`. Never blocks waiting for keyboard input.
- `--json` → full `QueryResult.model_dump(mode="json")` (columns + rows + elapsed_ms).
- No `--param`. Callers debugging ad-hoc paste literals; scripting callers use the Python client.
- **Always** sends `read_only: true`. The server enforces at driver level (`session.execute_read`); even `CREATE` in the Cypher string is rejected by Neo4j.

Text default: aligned table of rows. When the rows are Neo4j node/rel values, render as `name=<...> ...` compactly.

## Error handling

Applies to all four commands; follows the pattern already established by `guru graph status`.

| Condition | Exit | stderr |
|---|---|---|
| `guru-graph` package not installed | 2 | `guru-graph is not installed.` |
| Daemon unreachable (`GraphUnavailable` in transport, 503, 426, stale socket) | 1 | `daemon: unreachable (<reason>)` |
| `kb`/`links` when target KB missing | 1 | `KB <name> not found` |
| `query` server returns 500 (malformed Cypher etc.) | 1 | `query failed: <detail>` — the `detail` field from the structured error body |

No stack traces on stderr. Unexpected exceptions (anything not `GraphUnavailable` / `HTTPException`) re-raise — bugs should be visible.

## Safety invariants (reviewer contract)

1. `query` MUST call `GraphClient.query(..., read_only=True)`. No flag in the CLI may flip this.
2. No CLI subcommand may call `GraphClient.upsert_kb`, `.delete_kb`, `.link_kbs`, `.unlink_kbs`.
3. A unit test asserts both of these by inspecting click's registered commands.

## Files

| File | Change |
|---|---|
| `packages/guru-cli/src/guru_cli/commands/graph.py` | Add `kbs`, `kb`, `links`, `query` commands (~100–150 lines total). |
| `packages/guru-cli/tests/test_graph_cli_reads.py` | **New.** 10–12 tests using click's `CliRunner` with a mocked `GraphClient`. |
| `packages/guru-cli/tests/test_graph_cli_safety.py` | **New.** The two invariants above (~20 lines). |

No changes to: `packages/guru-graph/**`, `packages/guru-core/**`, `packages/guru-server/**`, `ARCHITECTURE.md`, the PR #35 design spec.

## Testing strategy

Unit tests only. The CLI is a thin layer over `GraphClient`; the client is already tested (unit, integration, `@real_neo4j`, BDD).

`CliRunner` with `mock.patch("guru_cli.commands.graph.GraphClient")` to swap in an `AsyncMock`. Each test:

1. Invokes one subcommand with synthesised args.
2. Asserts on stdout (for text) or `json.loads(stdout)` (for `--json`).
3. Asserts the client method was called with the expected kwargs (no mutation methods).

Cases to cover:
- `kbs` → list with 0 / 1 / many KBs, text + JSON, `--prefix`, `--tag`.
- `kb` → existing / missing, text + JSON.
- `links` → each direction, existing / empty results, text + JSON.
- `query` → positional arg, stdin, `--json`, Cypher error (server 500), `read_only=true` verified in the mock call.
- `GraphUnavailable` → exit 1 + stderr for every command.
- Safety: `upsert_kb` / `delete_kb` / `link_kbs` / `unlink_kbs` never appear in the click command tree and are never called from any command function.

## Success criteria

- All new tests pass.
- `uv run guru graph --help` lists the four new subcommands after the existing three.
- `uv run guru graph kbs` against a running daemon with KBs renders a readable table.
- `uv run guru graph query 'MATCH (k:Kb) RETURN count(k) AS n'` returns a single-row table.
- `uv run guru graph query --json 'RETURN 1 AS x'` outputs parseable JSON.
- No regression in the existing three `guru graph` commands.
