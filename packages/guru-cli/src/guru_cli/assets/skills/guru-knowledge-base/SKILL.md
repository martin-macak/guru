---
name: guru-knowledge-base
description: >
  Use when working in a guru-managed codebase — when discovering, investigating,
  or drawing conclusions about APIs, classes, functions, or cross-file relationships.
  Establishes how to search, navigate, annotate, and curate the project's durable
  knowledge base so derived insight compounds across sessions rather than being
  re-derived each time.
---

## 1. What this is

The guru KB is a LanceDB vector index (always on) plus an optional Neo4j-backed
structural graph. Every indexed file becomes a `(:Document)` with sub-artifacts
(sections, modules, classes, functions). Annotations are durable, first-class
nodes that hang off any artifact via `ANNOTATES` edges.

## 2. Why this matters

Derived insight is the scarcest artifact in software engineering — and the most
wasted. Every gotcha, cross-file connection, and behavioural quirk evaporates at
session end unless captured. Curating the KB turns one session's work into every
future session's starting context. Treat the KB as a co-author, not a search
index.

## 3. How to discover

`search(q)` returns both doc-chunks and artifact-chunks; pivot via
`metadata.artifact_qualname` to jump from text into structure. Use `graph_find`
for structural lookups by name or qualname prefix. `graph_describe(node_id)`
returns one node with annotations and links inline (single round-trip).
`graph_neighbors(node_id, depth=1, rel_type="RELATES", kind="calls")` for typed
traversal. Defer `graph_query` to `references/discovery.md` — it is last-resort.

## 4. When to write

After a non-trivial investigation. When a user correction teaches something
non-obvious. When you spot a cross-artifact relation the parser missed. Always
`graph_describe` the target first to check for an existing annotation — dedup
or update rather than duplicate.

## 5. When NOT to write

Don't re-state what the code already says. Don't summarise trivially. Don't
store ephemeral or session-specific thoughts. Don't invent new kinds — extend
with `tags` instead.

## 6. Curation loop

When `graph_orphans()` returns items, triage each: `graph_reattach_orphan` if a
refactor renamed the target, `graph_delete_annotation` if it's obsolete, or
leave it untouched and surface to the human if the decision is unclear.

## 7. Graph disabled

If any `graph_*` tool returns `{"status":"graph_disabled"}`, this project is
vector-only — fall back to `search()` and stop.

## 8. Deep dives

- `references/model.md` — schema and identity rules
- `references/discovery.md` — navigation patterns + Cypher last-resort
- `references/curation.md` — write policy and dedup
- `references/annotation-shape.md` — kind vs tag taxonomy
- `references/linking-patterns.md` — when each `ArtifactLinkKind` applies
- `references/orphans.md` — triage workflow
