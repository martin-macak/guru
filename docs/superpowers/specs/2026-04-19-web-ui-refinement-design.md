# Web UI Refinement — Design

**Date:** 2026-04-19
**Status:** Approved for planning
**Scope:** Web UI (`packages/guru-web`) + supporting server endpoints + new sync
invariant in `guru-server`. Not a rewrite of ingestion, LanceDB schema, or graph
schema.

## Problem

The workbench web UI shipped in `775a14c` has accumulated conceptual and visual
bloat that blocks the primary user journey:

1. **"Artifact" is a hallucinated second class.** The UI models indexed
   markdown documents and code-extracted graph nodes (Python functions, OpenAPI
   routes) under a shared "artifact" umbrella, plus a hardcoded mock list of
   "graph plan" entities in `packages/guru-web/src/lib/state/workbench.ts`.
   Users only care about indexed documents.
2. **The main surface is cramped.** A fixed three-column layout (`240px | 1fr |
   280px`) with max-width `7xl` never lets the active surface occupy the full
   window.
3. **Documents are second-class in navigation.** The Investigate surface
   search is backed by mock data. Documents cannot be "taken to" the graph.
   Only artifacts unlock graph navigation.
4. **The graph canvas has no stable orientation.** There is no notion of a
   persistent root or knowledge-base node; users get lost after a few expansions.
5. **Graph queries do not project into the graph.** The Query page button is
   inert, and the `POST /graph/query` endpoint's response is not rendered on
   the canvas.
6. **No LanceDB ↔ graph sync invariant.** Documents can be in LanceDB without
   a graph counterpart (and vice versa) with no detection or healing.

## Goals

- The active surface occupies the entire window (minus a thin top menu bar and
  an optional right pane).
- Remove the "artifact" concept from the UI entirely. The UI vocabulary is
  **documents**.
- User can list documents, similarity-search them, view content, see
  LanceDB + graph metadata, and jump from a document into the graph with that
  document focused.
- The graph canvas always presents a stable 2-level orientation: a synthetic
  federation root (client-only) and one or more knowledge-base nodes.
- Node click incrementally expands the canvas with the clicked node's neighbors.
- Whenever a node is selected, the path from selection through local KB to the
  federation root is drawn as a distinct, dashed hierarchy overlay.
- Cypher queries project their result set into the canvas (replacing non-root
  nodes), with a one-click return to the prior exploration state.
- LanceDB and the graph stay in sync whenever the graph daemon is enabled.
  Re-enabling, pruning, or restarting never leaves permanent drift.

## Non-goals

- No redesign of the ingestion pipeline, LanceDB schema, or graph schema
  beyond the sync plumbing.
- No removal of the Python / OpenAPI parsers. They continue to populate the
  graph for MCP and CLI consumers; the web UI simply filters their nodes out.
- No changes to the TUI.
- No authentication or multi-user functionality.

## Architecture

### Package boundaries

- `packages/guru-web` — the React/Vite workbench. Owns UI state, layout, and
  presentation. Talks to `guru-server` via REST over the existing web runtime.
- `packages/guru-server` — gains a `SyncService` that enforces the LanceDB ↔
  graph invariant, and three new REST endpoints (`POST /documents/search`,
  `GET /graph/roots`, `GET /sync/status`, `POST /sync/reconcile`). Existing
  endpoints stay shape-compatible; only graph-neighbor payloads gain a
  server-side filter.
- `packages/guru-graph` — unchanged in scope. Still the only component that
  talks to Neo4j.
- `packages/guru-core` — may gain shared types (`DocumentSearchHit`,
  `SyncStatus`, `GraphRootsPayload`) used by both server and web.
- `packages/guru-mcp`, `packages/guru-cli` — unchanged.

### UI vocabulary

- The word **artifact** is removed from all UI strings, component names, file
  names, and state shapes in `packages/guru-web/`. Every reference becomes
  **document**.
- The hardcoded `workbenchEntities` list and `investigateResults` mock in
  `packages/guru-web/src/lib/state/workbench.ts` are deleted. All data is
  fetched from `guru-server`.
- Code-extracted graph-only nodes (Python functions, OpenAPI routes) remain in
  the graph DB for MCP and CLI consumers. The web UI filters every graph
  payload to document-kind nodes only, at the server boundary (see endpoint
  changes below). The UI never receives, renders, or counts them.

### Surfaces

Three surfaces selectable from a thin top menu bar:

| Surface     | Purpose                                              |
|-------------|------------------------------------------------------|
| `Documents` | List, search, view document detail, jump to graph    |
| `Graph`     | Explore the knowledge graph; run Cypher queries      |
| `Status`    | Server / graph / federation health and sync state    |

The menu bar is approximately 32 px tall, contains only surface links plus a
project identifier, and never reflows the content below it.

### Layout

Every surface has the same skeleton:

```
┌─────────────────────────────────────────────────┐
│ Menu bar (Documents · Graph · Status)           │
├─────────────────────────────────────────────────┤
│                                   │             │
│   Main surface content            │  Metadata   │
│   (fills remaining width)         │  pane       │
│                                   │  (closeable)│
│                                   │             │
└─────────────────────────────────────────────────┘
```

- The main area occupies the full viewport width when the metadata pane is
  closed. No enforced max-width.
- The metadata pane is ~320 px when open. When closed it collapses to an icon
  strip (~32 px) with a reopen affordance.
- Open/closed state is persisted per-surface in `localStorage` under
  `guru.workbench.paneState.<surface>`.

### Documents surface (detail)

Three vertical regions inside the main area:

```
┌───────────┬──────────────────────────────┐
│  List     │  Detail (center)             │
│           │                              │
│  (~30%)   │                              │
│           │                              │
└───────────┴──────────────────────────────┘
```

- **List (left, ~30%)**: paginated list of `DocumentListItem` from
  `GET /documents`. Row = title + excerpt. Selected row highlighted. A search
  input sits at the top of the list region (not in the global menu bar). Typing
  into it calls `POST /documents/search`; results replace the list. A clear
  button restores the full list.
- **Detail (center)**: markdown rendering of the selected document via
  `GET /documents/{path}`. Above the rendered content: a small header with the
  document title and a `Go to graph` button.
- **Metadata pane (right, closeable)**: two sections.
  - *LanceDB*: path, chunk count, token count, last-ingested time, tags.
  - *Graph*: node id, degree, links grouped by `LinkKind` (each link is
    clickable → navigates to the target document or opens it in Graph surface).
  - Section hidden if the graph daemon is disabled.

`Go to graph` dispatches a client-side navigation to the Graph surface with
the document's graph node id as the focus target.

### Graph surface (detail)

Full-bleed ReactFlow canvas with an optional right metadata pane.

```
┌──────────────────────────────────┬───────────┐
│                                  │           │
│         Graph canvas             │ Metadata  │
│         (ReactFlow)              │ (closeable│
│                                  │ )         │
│                                  │           │
└──────────────────────────────────┴───────────┘
```

Canvas composition at all times:

- **Federation root** — a pinned, client-only synthetic node labelled
  "Federation". Not stored in the graph. Never removed from the canvas.
- **Knowledge-base nodes** — one per `KbNode` known to the server (the local
  KB plus any federated peers from the federation registry). Loaded once on
  surface mount via `GET /graph/roots`. Never removed from the canvas by node
  clicks (only by an explicit reset to a different federation context, which
  is out of scope).
- **Document nodes** — added by user actions (deep link from Documents surface,
  clicking a KB or document node, or running a query).

Behaviors:

1. **Initial state.** Canvas shows only the federation root and KB nodes.
2. **Deep link from Documents.** URL or in-app navigation carries a focus node
   id. On mount, canvas loads the focused document node, fetches its neighbors
   via `GET /graph/neighbors/{id}`, and merges them in. The focused node is
   visually highlighted and the path-to-root overlay is drawn.
3. **Node click → incremental expand.** Clicking any non-root node fetches
   that node's neighbors and merges them into the current canvas. Already-
   present nodes are deduplicated by id; new edges merged. No existing nodes
   are removed. The clicked node becomes the new "selected" node.
4. **Path-to-root overlay.** Whenever a non-root node is selected, a dashed
   hierarchy overlay is rendered from selection → local KB node → federation
   root. Hierarchy overlay edges are visually distinct (dashed, lighter color)
   from real graph edges. The overlay updates on every selection change.
5. **Clear / reset.** A small "Clear" control on the canvas removes all
   document nodes, returning the canvas to root + KBs only.
6. **Cypher query — replace projection.** A "Query" button on the Graph
   surface opens an inline Cypher input (textarea + Run). Running calls
   `POST /graph/query` and, on success, **replaces** the canvas: federation
   root + KB nodes stay pinned; every other node and edge is wiped and
   repopulated from the query result `{nodes, edges}`. A `Back to exploration`
   control restores the pre-query canvas state. Empty result set shows an
   inline banner; the canvas reverts to root + KBs (no stale nodes). Query
   errors surface inline; the canvas stays unchanged.
7. **Graph daemon disabled.** Surface shows a disabled banner; no canvas.

The right metadata pane shows the same LanceDB + graph metadata as the
Documents surface, for the currently selected graph node.

### Status surface

Single-pane dashboard. No side panes. Sections:

- Project identity (name, root).
- Server health (web runtime, uptime).
- Graph daemon (enabled/disabled, reachability, version).
- Federation registry summary (count, names).
- Index counts: LanceDB document count, graph document-node count, **drift
  count** (documents that exist in one store but not the other).
- "Reconcile now" button — calls `POST /sync/reconcile`, disabled while a
  reconcile is in flight, updates counts in place.
- Last reconciled timestamp.

## LanceDB ↔ Graph sync invariant

A new `SyncService` lives in `packages/guru-server/src/guru_server/sync.py`.
It is the authoritative enforcer of the invariant:

> For every document indexed in LanceDB, a corresponding document-kind graph
> node exists under its local KB whenever the graph daemon is enabled.

### Triggers

- **On document ingest** (graph enabled): after LanceDB upsert succeeds,
  upsert the graph node in the same unit of work. Ingest returns success only
  if both succeed, or both are idempotently no-ops.
- **On document ingest** (graph disabled): upsert LanceDB. Record the
  document id in a pending-sync queue (in-memory; recomputed on startup from
  LanceDB vs graph diff, so it survives restarts).
- **On document delete**: delete from LanceDB then delete the graph node (or
  enqueue for the pending-sync queue if graph is disabled).
- **On graph enable** (from disabled): backfill — walk LanceDB, create any
  missing graph nodes, delete any graph nodes that no longer have a LanceDB
  counterpart (e.g. from a prior delete while disabled).
- **On server startup** (graph enabled): run a reconcile pass. Compute diff;
  heal.
- **On `POST /sync/reconcile`**: run a reconcile pass synchronously; return
  the resulting status.

### Reconciliation algorithm

```
lancedb_ids   = set(doc.id for doc in LanceDB.list_all())
graph_ids     = set(node.id for node in GraphBackend.list_document_nodes(kb))
missing_nodes = lancedb_ids - graph_ids
stale_nodes   = graph_ids  - lancedb_ids

for id in missing_nodes:
    GraphBackend.upsert_document_node(kb, LanceDB.get(id))

for id in stale_nodes:
    GraphBackend.delete_document_node(kb, id)

return SyncStatus(
    lancedb_count=len(lancedb_ids),
    graph_count=len(graph_ids) + len(missing_nodes) - len(stale_nodes),
    drift=0,
    last_reconciled_at=now,
)
```

A reconcile is safe to run concurrently with ingestion because both operations
go through `SyncService` and acquire a per-KB lock for the duration of the
diff-and-heal pass. Ingestion during a reconcile is serialised.

### Observability

- Drift count exposed on the Status surface and via `GET /sync/status`.
- Structured logs at info level for every reconcile (counts, duration).
- Warn-level log if drift is detected at server startup.

## Server endpoints

### New

- `POST /documents/search`
  - Request: `{"query": str, "limit": int = 20}`
  - Response: `{"hits": [{"path": str, "title": str, "excerpt": str,
    "score": float}]}`
  - Thin wrapper over the existing vector search path.
- `GET /graph/roots`
  - Response: `{"federation_root": {"id": "federation", "label": "Federation"},
    "kbs": [KbNode, ...]}`
  - Federation root is synthesised server-side for convenience; the web UI
    could compute it too, but centralising the shape keeps the payload a
    single fetch.
- `GET /sync/status`
  - Response: `{"lancedb_count": int, "graph_count": int, "drift": int,
    "last_reconciled_at": datetime | null, "graph_enabled": bool}`.
- `POST /sync/reconcile`
  - Request: `{}` (no body).
  - Response: same shape as `GET /sync/status` after reconciliation.
  - Returns `409` if graph is disabled.

### Changed

- `GET /graph/neighbors/{node_id}` — response filtered **server-side** so the
  web UI never sees code-extracted graph-only nodes. The filter is applied via
  a new `kind` filter in the graph daemon's neighbor query. MCP and CLI
  consumers continue to call the unfiltered variant.
- `POST /graph/query` — response shape standardised as `{"nodes": [...],
  "edges": [...]}` where each node carries `id`, `label`, `kind`, and a
  `kb` field; each edge carries `source`, `target`, `kind`. Read-only
  enforcement unchanged. The server filters the synthetic federation-root id
  out of query results so clients cannot accidentally surface it as a real
  graph node.

### Unchanged

- `GET /documents`, `GET /documents/{path}`, `GET /documents/{path}/sections/*`.
- All other `/graph/*` endpoints.

## State and routing (web)

Client-side routes:

- `/documents` — list. `?q=` for the search term; typing updates debounced.
- `/documents/:path` — detail view. List still visible on the left.
- `/graph` — canvas, empty selection → root + KBs only.
- `/graph?focus=:nodeId` — canvas pre-focused on a specific node.
- `/status` — status surface.

Selection state (selected document in Documents surface, selected node in
Graph surface) lives in a thin workbench store, not duplicated per surface.
The pane-open/closed state is persisted in `localStorage`.

## Testing strategy

### BDD features (acceptance)

Four new feature files under `tests/e2e/features/`:

- **`web_documents.feature`** — list, similarity search, detail, metadata
  pane, Go to graph.
- **`web_graph.feature`** — root/KB rendering, incremental expand,
  path-to-root overlay, Cypher query projection, graph-disabled state.
- **`sync_invariant.feature`** — ingest-with-graph, ingest-without-graph,
  enable after ingest, disable/re-enable, prune and reconcile, delete
  propagation, startup reconcile, drift surfacing.
- **`web_status.feature`** — healthy render, disabled graph render, reconcile
  button.

Web-surface features are driven from behave steps using **Playwright** as a
new test-only dependency (added to the workspace's dev dependency group, not
to any runtime package). The web UI is served via the existing
`web_runtime.py` FastAPI static mount; the harness boots a test server with a
seeded LanceDB and an optional graph daemon. Plan step zero validates that
Playwright adoption is acceptable with the user before writing harness code.

### Unit tests

- `packages/guru-server/tests/test_sync_service.py` — reconcile algorithm,
  locking, graph-disabled path.
- `packages/guru-server/tests/test_sync_endpoints.py` — `/sync/status`,
  `/sync/reconcile`, `/documents/search`, `/graph/roots` shape.
- `packages/guru-web/src/**/*.test.tsx` — component tests for Documents list,
  detail, metadata pane, Graph canvas reducer, path-to-root computation,
  Cypher-projection replace/restore.

### Test tags

- `@real_neo4j` continues to gate tests that need Neo4j.
- New `@real_lancedb` unused; LanceDB is always exercised (it's always
  available locally).

## Invariants (constitution addendum)

Append to `ARCHITECTURE.md`:

1. *The web UI never surfaces non-document graph nodes.* All graph payloads
   consumed by `guru-web` are filtered server-side to document-kind nodes.
2. *LanceDB is the authoritative source of document identity.* The graph
   stores document-kind nodes only as a mirror. Sync conflicts are resolved
   in LanceDB's favor.
3. *The federation root is UI-only.* It is never stored in the graph and
   must not appear in graph query results.

## Migration / rollout

- Single release. No feature flag.
- On first launch after upgrade, the server's startup reconcile will heal any
  drift that the previous (unsynced) build left behind.
- No user-facing migration step; the old workbench mock data simply disappears.

## Open questions

None remaining from brainstorming. Items flagged for confirmation during
review:

- Full removal of the Python / OpenAPI parsers is **not** proposed. They are
  preserved for MCP / CLI consumers. Confirm during review if this should
  change.

## Related files

- `packages/guru-web/src/features/investigate/InvestigatePage.tsx` — to be
  renamed/restructured as Documents surface.
- `packages/guru-web/src/features/graph/GraphPage.tsx` — path-to-root overlay,
  incremental expand, Cypher projection.
- `packages/guru-web/src/features/query/QueryPage.tsx` — removed (merged into
  Graph surface).
- `packages/guru-web/src/features/operate/OperatePage.tsx` — becomes Status
  surface.
- `packages/guru-web/src/lib/state/workbench.ts` — mock data removed.
- `packages/guru-server/src/guru_server/web_runtime.py` — no changes.
- `packages/guru-server/src/guru_server/api/documents.py` — add `/search`.
- `packages/guru-server/src/guru_server/api/graph.py` — filter neighbors,
  add `/roots`, standardise query response.
- `packages/guru-server/src/guru_server/sync.py` — new module.
- `packages/guru-server/src/guru_server/main.py` — wire `SyncService`,
  startup reconcile.
- `packages/guru-core/src/guru_core/graph_types.py` — shared types.
