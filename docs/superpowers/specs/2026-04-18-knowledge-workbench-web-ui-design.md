# Knowledge Workbench Web UI Design

**Date:** 2026-04-18  
**Status:** Draft  
**Follows:** `ARCHITECTURE.md`, `docs/superpowers/specs/2026-04-18-knowledge-workbench-tui-design.md`, `docs/superpowers/specs/2026-04-18-artifact-graph-knowledge-base-design.md`

---

## Problem

Guru now has a usable TUI knowledge workbench, but it still lacks a browser-based surface for richer document inspection, table views, and graph interaction. The terminal UI is appropriate for keyboard-first workflows, but it is the wrong medium for persistent panes, richer data tables, and interactive graph exploration.

At the same time, the project architecture must remain server-centric:

- `guru-server` remains the only per-project backend surface.
- Browser code must not talk directly to LanceDB, Ollama, Neo4j, `guru-graph`, or Unix domain sockets.
- The browser UI must stay a thin client over `guru-server`, just as the TUI stays a thin client over `guru-core`.

The missing piece is a production-grade browser workbench that:

- mirrors the TUI's core capabilities
- uses browser-native layouts and interactions
- is served automatically by `guru-server`
- stays optional at runtime even though enabled by default

## Goals

1. Ship a browser-based knowledge workbench that matches the current TUI's core capability set.
2. Use a browser-first layout rather than copying the TUI literally.
3. Keep `guru-server` as the only browser-facing backend surface.
4. Support local frontend development with Vite while serving bundled assets from `guru-server` in normal runtime.
5. Start a localhost web surface automatically when `guru-server` starts, on an ephemeral port.
6. Keep browser auto-open disabled by default, but support explicit open via `guru server web-open`.
7. Use React Flow for graph rendering while preserving the TUI's selection-centered subgraph model.
8. Preserve degraded operation: if the web surface fails to start, `guru-server` still runs.

## Non-Goals

- No browser-only write workflows in v1.
- No direct browser access to `guru-graph`.
- No replacement of the TUI; the browser UI is an additional first-party surface.
- No graph curation UI in v1: no annotation CRUD, manual linking, unlinking, or orphan reattachment flows.
- No production dependency on a standalone Vite server.
- No requirement that frontend assets be present for `guru-server` startup to succeed.
- No public remote web hosting; the runtime web UI is localhost-only.

---

## Product Shape

The web UI is an **embedded web companion** for Guru: a browser-native knowledge workbench served and managed by `guru-server`.

Unlike the TUI, the browser UI should not be primarily mode-driven. It should use a persistent application shell with richer concurrent context:

- persistent navigation/sidebar
- central active work area
- contextual right-side inspector
- top-level switching between `Investigate`, `Graph`, `Query`, and `Operate`

### Primary surfaces

1. `Investigate`
   Default landing surface. Search, results, knowledge tree, and inspector coexist in a browser-friendly layout.
2. `Graph`
   Selection-centered React Flow graph with richer browser affordances: drag, zoom, fit-view, minimap, and edge inspection.
3. `Query`
   Read-only advanced graph query surface, intentionally separate from default investigation.
4. `Operate`
   Server status, graph status, indexed-document visibility, jobs, and operational controls.

### v1 parity stance

The first web release is **parity plus light browser upgrades**:

- same core capabilities as the TUI
- richer graph interactions
- better tables and inspectors
- better deep-linking and multi-pane context

The first web release does **not** expand into new write workflows.

---

## Architecture

The web UI should live in a new workspace package:

```text
packages/
  guru-web/
    src/
    public/
    tests/
    vite.config.ts
    tsconfig.json
```

Recommended stack:

- React
- TypeScript
- Vite
- shadcn/ui
- React Router
- React Flow
- TanStack Query
- Vitest
- React Testing Library
- jsdom

### Thin-client boundary

The browser app talks only to `guru-server` over localhost HTTP.

It must not:

- open UDS connections
- import server internals
- call `guru-graph` directly
- access LanceDB, Ollama, or Neo4j directly

This mirrors the TUI constitutionally, even though the transport is different.

### Development runtime

In development:

- `guru-web` runs under Vite on its own localhost port
- developers open the Vite URL directly
- `guru-server` may expose browser-compatible local API routes and dev CORS allowances only for local development

The dev server is a frontend developer convenience, not part of production/runtime architecture.

### Production/runtime model

In normal runtime:

- `guru-web` is built into static assets
- `guru-server` serves those assets on an ephemeral localhost port
- that web runtime is enabled by default
- browser auto-open is disabled by default
- `guru server web-open` opens the current allocated URL explicitly

If static assets are missing or the web surface cannot start:

- `guru-server` still starts
- status surfaces report `web: unavailable`
- CLI/TUI functionality remains intact

This keeps the browser UI optional operationally, even if enabled by default in config.

---

## Runtime and Configuration

The web surface should introduce configuration under Guru's existing config model.

Recommended config keys:

```json
{
  "web": {
    "enabled": true,
    "autoOpen": false
  }
}
```

Semantics:

- `web.enabled`
  Controls whether `guru-server` attempts to start the runtime web surface.
  Default: `true`.
- `web.autoOpen`
  Controls whether a browser is opened automatically on direct human-run server starts.
  Default: `false`.

In v1, even if `autoOpen` exists, the effective default behavior remains manual:

- URL is surfaced in status/logs
- `guru server web-open` opens it explicitly

### Web runtime ownership

`guru-server` owns:

- ephemeral localhost port allocation
- lifecycle of the runtime web listener
- reporting current web availability and URL
- `web-open` behavior

The runtime web port is not a new backend service boundary. It is a browser-facing façade of `guru-server`.

---

## Browser Shell

The web shell should be browser-first rather than a direct clone of the TUI.

Recommended layout:

- Left sidebar
  App navigation and knowledge-tree access.
- Top bar
  Project identity, connection state, refresh/open actions, surface switcher.
- Center workspace
  Active surface: `Investigate`, `Graph`, `Query`, or `Operate`.
- Right inspector
  Artifact/document metadata, properties, summaries, edge information, or status detail.

Optional secondary surfaces:

- bottom drawer for query results or logs
- collapsible knowledge tree and inspector panels

This keeps the browser UI spatially richer while preserving the same conceptual model as the TUI.

---

## Components

The browser app should be divided into three clear layers:

1. `Shell and routing`
2. `Feature modules`
3. `API and shared state`

### Shell and routing

Responsibilities:

- app shell composition
- routing and URL state
- global providers
- layout persistence
- keyboard shortcut registration

Suggested structure:

```text
packages/guru-web/src/app/
  App.tsx
  router.tsx
  providers.tsx
  layout/
```

### Feature modules

Suggested structure:

```text
packages/guru-web/src/features/
  investigate/
  graph/
  query/
  operate/
  knowledge-tree/
  inspector/
```

Responsibilities:

- feature-local components
- feature hooks
- feature-local view-model shaping
- surface-specific commands

### API and shared state

Suggested structure:

```text
packages/guru-web/src/lib/
  api/
  state/
  routing/
  graph/
```

Responsibilities:

- typed HTTP client
- endpoint wrappers
- server-state query hooks
- cross-surface UI state
- URL synchronization helpers

### Shared state split

The web app should explicitly separate:

- `server state`
  fetched and cached via TanStack Query
- `UI/workbench state`
  current selection, panel state, graph focus, query draft, layout preferences

This avoids mixing refetchable backend state with browser-session interaction state.

---

## Surface Contracts

### Investigate

Purpose:

- default browser workflow
- search, inspect, and transition into graph/query/operate

Behavior:

- unified search entry
- results in richer table/list form than the TUI
- deep inspector for selected item
- reveal in knowledge tree
- jump to graph for selected artifact

### Graph

Purpose:

- browser-native structural exploration

Behavior:

- preserves the TUI's selection-centered subgraph model
- uses React Flow for rendering and interaction
- supports zoom, pan, fit-view, minimap, drag
- keeps the semantic source of truth in shared selection and fetched neighborhood state, not in React Flow internals

The graph is still neighborhood-bounded. It is not a freeform giant-canvas editor.

### Query

Purpose:

- expert read-only graph queries

Behavior:

- separate from default search
- tabular results first
- selected result rows can promote document/artifact focus into shared selection

### Operate

Purpose:

- runtime visibility and safe actions

Behavior:

- show server status
- show graph status
- show indexed-document summaries and job snapshots
- expose safe operational actions already supported by server surfaces

---

## Data Flow

The web app should use one-way data flow wherever possible:

1. user input updates route/UI state
2. feature hook issues typed request through the API client
3. `guru-server` executes the request and proxies graph access internally if needed
4. response is normalized into browser view models
5. shared selection/focus state updates the rest of the shell

### URL state

URL state should be first-class in the browser. At minimum, it should capture:

- active surface
- current search query
- selected document id
- selected artifact id
- graph depth
- query surface state where relevant

This enables:

- refresh-safe navigation
- copy/pasteable deep links
- back/forward support

### Shared selection model

The browser should reuse the same conceptual cross-surface selection model as the TUI:

- selected document id
- selected artifact/node id
- current graph focus
- current results context

Selecting a result in `Investigate`, a node in `Graph`, or a row in `Query` should all converge into this shared selection model.

### Graph flow

React Flow is a renderer and interaction engine, not the authority for graph state.

Authoritative graph state should be:

- focused node id
- requested depth
- fetched bounded neighborhood

This keeps behavior consistent with the TUI and prevents browser-only graph drift.

---

## Browser-Facing Server Surface

The web app needs browser-oriented server routes, but these should still be thin wrappers over existing Guru server functionality.

Recommended server-side additions:

- web runtime boot/config endpoint
- browser-oriented API routes under `/api/...`
- runtime web URL/status reporting
- `guru server web-open` command

### Boot/config payload

The browser should load a small runtime bootstrap payload from `guru-server`, for example:

- project identity
- current capability flags
- whether graph is enabled
- current web base URL/base path if needed
- version/protocol hints

This avoids hardcoded frontend assumptions and makes degraded states explicit.

### API shape

The browser's API should remain server-centric:

- search/read/query/operate endpoints live on `guru-server`
- graph reads are proxied through `guru-server`
- the browser does not speak to `guru-graph` directly

The web UI is therefore another client of Guru server APIs, not a second backend.

---

## Error Handling

The browser UI must treat degraded runtime as normal.

### Runtime states

- `web unavailable`
  `guru-server` is healthy, but runtime web serving is unavailable.
- `graph disabled`
  normal degraded state; graph UI explains that graph is disabled.
- `graph unavailable`
  graph surface degrades; investigate/query/operate still work.
- `server unavailable`
  browser shows reconnect/retry state.
- `query error`
  isolated to the query surface.
- `empty states`
  explicit views for no results, no documents, no neighbors, no jobs, no selection.

### Severity classes

- `info`
  empty state, graph disabled, no neighbors
- `recoverable`
  graph unreachable, failed poll, timed-out query, transient web runtime issue
- `blocking`
  no server connection, incompatible protocol, malformed runtime boot payload

### Startup behavior

If web startup fails:

- `guru-server` continues to run
- status routes and CLI surfaces report `web: unavailable`
- browser-specific features are unavailable, but the project remains usable

This is mandatory because the web UI is enabled by default but may not always be available.

---

## Testing

The web app should use a single browser-app test stack:

- Vitest
- React Testing Library
- jsdom

No Jest is required in v1.

### Test layers

#### Unit tests

Cover:

- pure helpers
- route parsers
- view-model mappers
- graph utility functions
- formatting logic

#### Integration tests

Cover:

- feature hooks
- shared state interactions
- typed API wrappers
- mocked API-client flows

#### React tests

Cover:

- page rendering in jsdom
- event firing
- state transitions
- visible output assertions
- no real browser required

#### Server-side tests

Add/extend tests for:

- web enabled/disabled behavior
- missing built assets => `web: unavailable`
- runtime web URL reporting
- `guru server web-open`
- browser API routes

### Priority browser coverage for v1

- investigate flow
- graph focus and depth changes
- query execution and row promotion
- operate polling and degraded-state rendering
- deep-link restoration
- graph disabled / graph unavailable / web unavailable states

Real browser E2E automation can come later. It is not required for the first design/implementation slice.

---

## File and Package Impact

Expected new package:

| Path | Purpose |
| --- | --- |
| `packages/guru-web/` | browser app package |
| `packages/guru-web/src/app/` | shell, routing, providers |
| `packages/guru-web/src/features/` | feature surfaces |
| `packages/guru-web/src/lib/api/` | typed frontend client |
| `packages/guru-web/src/lib/state/` | UI/workbench state |
| `packages/guru-web/src/test/` | shared frontend test helpers |

Expected server changes:

| Path | Purpose |
| --- | --- |
| `packages/guru-server/src/guru_server/...` | runtime web serving, browser API routes, status/open wiring |
| `packages/guru-cli/src/guru_cli/cli.py` | `guru server web-open` and related CLI integration if needed |

---

## Acceptance Criteria

1. Starting `guru-server` with default config attempts to start a localhost web surface on an ephemeral port.
2. If the web runtime cannot start, `guru-server` still starts and reports `web: unavailable`.
3. `guru server web-open` opens the allocated runtime browser URL.
4. The browser app talks only to `guru-server`, not directly to `guru-graph`.
5. The browser app supports `Investigate`, `Graph`, `Query`, and `Operate` surfaces with parity to the current TUI scope.
6. Graph rendering uses React Flow but preserves a selection-centered bounded-neighborhood model.
7. Development can run the frontend under Vite without changing production/runtime architecture.
8. Frontend tests run under Vitest + React Testing Library + jsdom without requiring a real browser.

