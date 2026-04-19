# Knowledge Workbench TUI Design

**Date:** 2026-04-18
**Status:** Draft
**Follows:** `ARCHITECTURE.md`, `docs/superpowers/specs/2026-04-18-artifact-graph-knowledge-base-design.md`

---

## Problem

`guru-cli` is still a click-only thin client. Running `guru` with no arguments prints a placeholder message even though the architecture explicitly reserves bare `guru` for a Textual TUI.

At the same time, the project now has enough read surfaces to justify a real interactive shell:

- semantic search over indexed chunks
- artifact-aware graph navigation
- indexed document and artifact browsing
- server / graph daemon status
- read-only graph query for debugging and investigation

The missing piece is a terminal UI that makes those capabilities discoverable and keyboard-driven without violating the server-centric architecture or turning the terminal into a poor graph canvas.

## Goals

1. Ship a Textual-based TUI as the default `guru` experience while preserving the existing click commands.
2. Make investigation the primary workflow: search, inspect, browse the knowledge tree, and jump into graph traversal without leaving the keyboard.
3. Model navigation around the knowledge base hierarchy, not the raw filesystem tree.
4. Provide a real graph experience in terminal form via a selection-centered subgraph, not a free-panning canvas.
5. Expose operational visibility and basic controls for guru-server and the optional graph daemon from the same TUI.
6. Keep v1 read-only on the graph surface: no annotation, linking, unlinking, or orphan triage workflows.
7. Preserve the constitution: the TUI remains a thin client over `guru-core`, and graph failure remains degradable rather than fatal.

## Non-Goals

- No filesystem explorer in v1.
- No graph curation UI in v1: no annotation CRUD, no manual link creation, no orphan reattachment.
- No freeform graph editor or spatial canvas metaphor.
- No attempt to expose every click subcommand as a dedicated full-screen panel.
- No direct backend access from widgets to guru-server, LanceDB, Ollama, Neo4j, or guru-graph internals.
- No replacement of the existing click CLI; the TUI is additive and becomes the default launch path.
- No plugin framework for arbitrary third-party TUI panels in v1.

---

## Product shape

The v1 product is a **mode-driven knowledge workbench**. One dominant center surface is always in focus. Side panels are contextual and toggleable rather than permanently occupying columns.

### Primary modes

1. `Investigate` — default mode. Unified investigation input, result list/detail, and fast transitions into the knowledge tree or graph.
2. `Graph` — selection-centered artifact traversal using a bounded neighborhood around the focused node.
3. `Query` — expert-mode read-only Cypher surface, intentionally separate from the default investigation input.
4. `Operate` — server and daemon health, indexed-document visibility, job snapshots, and basic control actions.

### Persistent shell elements

- Lightweight header: current project/KB, mode, connection state.
- Lightweight footer: mode-specific key hints and transient status.
- Toggleable knowledge tree panel.
- Toggleable detail/status panel.

This is explicitly **not** a three-pane always-on dashboard. The TUI should maximize space for the active task.

---

## Architecture

The TUI lives under a new package subtree:

```text
packages/guru-cli/src/guru_cli/tui/
  app.py
  session.py
  state.py
  bindings.py
  controllers/
  widgets/
  view_models/
```

Entry-point behavior:

- bare `guru` launches the TUI
- `guru tui` launches the same TUI explicitly
- all existing click commands remain available and unchanged

This preserves the thin-client boundary:

- the TUI talks only to `GuruClient` / `GraphClient` through `guru-core`
- the TUI never imports guru-server storage/indexer internals
- the TUI never imports guru-graph backend internals

The TUI architecture should be event-driven rather than widget-driven. Widgets render state and emit intents. Controllers and the session layer own all IO.

---

## Components

### `WorkbenchApp`

Owns:

- Textual app lifecycle
- global mode switching
- app-wide key bindings
- startup / reconnect flow
- registration of contextual panels
- publication of shared state changes

`WorkbenchApp` should stay orchestration-only. It should not contain backend call logic or mode-specific business rules.

### `GuruSession`

Single async façade over `GuruClient` and `GraphClient`.

Responsibilities:

- perform all backend requests
- translate graph-disabled / graph-unavailable responses into typed TUI outcomes
- manage polling for health and jobs
- own cancellation and in-flight request replacement
- normalize backend payloads into TUI view models

This is the only TUI-side object allowed to talk to `guru-core` clients directly.

### `WorkbenchState`

Single shared state object for cross-mode context.

Must contain only durable, cross-surface facts such as:

- current mode
- selected KB / project root
- selected document id
- selected artifact/node id
- latest investigation query
- latest search results
- current graph neighborhood
- latest query results
- server and graph health
- job snapshots
- panel visibility

It should not become an unstructured dump of every widget-local concern.

### Mode controllers

- `InvestigateController`
- `GraphController`
- `QueryController`
- `OperateController`

Each controller owns:

- input handling for its mode
- commands and keyboard actions
- refresh policy
- writes into `WorkbenchState`

Each controller does **not** own shell lifecycle or direct widget rendering.

### Widgets

Widgets should be small and composable. Expected v1 widgets:

- `KnowledgeTreeWidget`
- `InvestigationInputWidget`
- `ResultsListWidget`
- `DetailPanelWidget`
- `GraphViewportWidget`
- `QueryEditorWidget`
- `QueryResultsWidget`
- `OperationsStatusWidget`
- `StatusBannerWidget`

The graph widget may use `netext` as its renderer, but the interaction model belongs to Guru, not to `netext`'s built-in `GraphView`.

---

## Mode contracts

### Investigate mode

Purpose: primary workflow.

Behavior:

- unified input defaults to semantic search
- artifact-aware search and structural lookup are accessible from the same investigation surface
- selecting a result updates shared focus
- detail panel shows document or artifact metadata
- actions allow reveal in knowledge tree, open detail, or jump into graph mode

The unified input is **not** raw Cypher. Advanced query stays separate.

### Graph mode

Purpose: terminal-native structural traversal.

Behavior:

- requires a focused artifact or document-derived artifact target
- renders a bounded, selection-centered neighborhood
- movement changes semantic focus, not viewport position
- depth changes requery the neighborhood
- opening detail or jumping back to investigation preserves the focused node

Recommended key model:

- `h/j/k/l` or arrows: move focus between visible nodes
- `Enter`: open focused node detail / promote selection
- `[` / `]` or `-` / `+`: decrease/increase neighborhood depth
- `Tab`: cycle visible neighbors when geometry is ambiguous
- `t`: reveal/focus same node in knowledge tree

### Query mode

Purpose: expert read-only graph debugging and investigation.

Behavior:

- separate screen from the main investigation input
- accepts read-only Cypher only
- shows tabular results first
- allows promoting a selected row back into shared document/artifact focus when resolvable

This mode should feel intentionally advanced, not casually mixed into search.

### Operate mode

Purpose: operational visibility and safe control actions.

Behavior:

- show guru-server health
- show graph daemon health when enabled
- show indexed document counts and relevant summary stats
- show active/recent jobs when the existing server status surface exposes them; otherwise fall back to last known indexing status and document counts
- provide basic controls such as start, stop, refresh, and reindex

This mode answers "is Guru healthy and what is it doing?" without forcing shell use.

---

## Knowledge tree

The left-side navigation model is a **knowledge tree**, not a filesystem tree.

The tree should represent the knowledge base hierarchy:

- KB root
- documents
- sub-artifacts only when they have been returned by artifact-aware surfaces already loaded in the session (for example artifact search hits, graph description, or graph neighbors)

Tree selection semantics:

- selecting a document updates shared document focus
- selecting an artifact updates shared node focus
- the active mode decides how to present the selected item in the center surface

The tree is a shared navigation widget available from any mode. It is not itself a top-level mode.

If the graph is disabled or unavailable, the tree still works with the best available document/artifact structure already present in the current surface data.

---

## Data flow

The workbench should use a mostly one-way flow:

1. user input reaches the active mode controller
2. controller calls `GuruSession`
3. `GuruSession` performs async backend work through `guru-core`
4. returned payloads are normalized into view models
5. `WorkbenchState` is updated
6. widgets react and re-render

### Investigation flow

- user enters a search in the unified investigation input
- `InvestigateController` dispatches semantic search by default
- results may include document chunks and artifact chunks
- selected result updates shared document/node focus
- detail panel optionally prefetches full artifact description

### Tree flow

- user selects a node in `KnowledgeTreeWidget`
- shared focus updates
- center surface re-renders according to the active mode

### Graph flow

- entering graph mode with a focused node triggers neighbor fetch
- graph widget receives a bounded neighborhood view model
- moving focus inside the graph updates shared selection
- depth change causes requery, not client-side geometric scaling

### Query flow

- user submits Cypher in advanced query mode
- results remain tabular by default
- selected rows with resolvable ids can become shared document/node focus

### Operate flow

- health and job views poll on an interval
- actions like start/stop/reindex are explicit commands
- long-running work updates status views rather than blocking input

---

## Graph rendering model

The default graph interaction model is **selection-centered subgraph traversal**.

Why:

- it preserves a real graph pane in terminal space
- it supports crisp keyboard traversal
- it avoids pretending the terminal is a free-panning visual canvas
- it keeps investigation centered on one artifact at a time

The graph view should render a bounded local neighborhood around the focused node. The viewport is conceptual rather than spatial. Changing selection can change the rendered subgraph.

### Renderer decision

`netext` is acceptable as a rendering primitive, but the TUI should own:

- focused node
- neighborhood depth
- selection transitions
- expansion / collapse policy
- graph-to-widget view-model adaptation

Do **not** couple v1 behavior to `netext`'s built-in Textual `GraphView` abstraction. A thin adapter layer is required so the renderer can be swapped without redesigning the app.

---

## Query model

The query model is hybrid:

- default investigation input for normal discovery work
- separate advanced query screen for raw Cypher

This avoids overloading the main search experience with expert-only syntax while still preserving an escape hatch for graph debugging.

The advanced query screen must enforce read-only semantics all the way through the existing backend contract.

---

## Error handling

The TUI must treat degraded graph behavior as normal, per the constitution.

### States

- **Server unavailable**: blocking recovery screen with retry/start guidance.
- **Graph disabled**: valid informational state; graph features explain unavailability without surfacing an error.
- **Graph unavailable**: degraded state; non-graph modes keep working.
- **Validation error**: local to the relevant mode, especially query mode.
- **Empty state**: explicit empty render, never blank space.

### Severity classes

- `Info`: graph disabled, empty result, no neighbors.
- `Recoverable`: timed-out refresh, graph unreachable, failed query execution.
- `Blocking`: no Guru project found, server cannot start, incompatible protocol.

### Recovery rules

- widgets never raise raw exceptions to the screen
- unexpected exceptions become visible bug states with enough context to debug
- recoverable failures must preserve keyboard responsiveness

---

## Testing strategy

The TUI test strategy should center on state transitions and controller behavior, not pixel-perfect snapshots.

### Unit tests

- `GuruSession` request/response translation
- controller behavior for mode switching, focus changes, and refresh logic
- graph disabled/unavailable normalization
- keyboard action dispatch

### Widget tests

- knowledge tree selection behavior
- graph widget focus/depth controls
- query results selection behavior
- status banner / empty-state rendering

### CLI integration tests

- bare `guru` launches TUI entrypoint
- `guru tui` launches the same entrypoint
- existing click commands remain unchanged

### BDD coverage

Add a TUI-focused feature covering:

- open app in initialized Guru project
- inspect server / graph status
- browse indexed documents via knowledge tree
- run investigation search
- jump from result to graph mode on an artifact
- execute read-only Cypher in query mode
- handle graph-disabled configuration cleanly

---

## File plan

Expected initial file ownership:

| File / subtree | Responsibility |
|---|---|
| `packages/guru-cli/src/guru_cli/tui/app.py` | `WorkbenchApp` and top-level shell wiring |
| `packages/guru-cli/src/guru_cli/tui/session.py` | async client façade and polling |
| `packages/guru-cli/src/guru_cli/tui/state.py` | shared workbench state models |
| `packages/guru-cli/src/guru_cli/tui/bindings.py` | centralized key bindings and action names |
| `packages/guru-cli/src/guru_cli/tui/controllers/` | per-mode logic |
| `packages/guru-cli/src/guru_cli/tui/widgets/` | visual primitives and contextual panels |
| `packages/guru-cli/src/guru_cli/cli.py` | bare `guru` / `guru tui` entrypoint integration |
| `packages/guru-cli/tests/` | TUI unit and integration tests |
| `tests/e2e/features/` | TUI BDD workflow coverage |

This ownership split is deliberate so parallel work can proceed without multiple agents editing one giant file.

---

## Success criteria

1. Running `uv run guru` launches a usable Textual workbench instead of a placeholder message.
2. Investigation is the default workflow and works entirely from the keyboard.
3. The knowledge tree navigates KB documents/artifacts, not the filesystem.
4. Graph mode centers on the selected artifact and supports bounded traversal without free-panning.
5. Query mode supports read-only Cypher without contaminating the default search UX.
6. Operate mode surfaces server/graph status and basic controls.
7. When the graph is disabled or unavailable, the TUI remains useful and does not crash.
8. The design remains compatible with the existing thin-client architecture and artifact-graph interfaces.
