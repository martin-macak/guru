# Orphan triage

An annotation becomes an **orphan** when its target is removed —
typically by a rename or refactor that changes the artifact's id.

## Workflow

1. **List**. `graph_orphans()` returns annotations whose target no
   longer exists.
2. **Inspect context**. Each orphan carries a `target_snapshot_json`
   field: the original target's id, label, and breadcrumb at the time
   the annotation was written. Read this first — it tells you what the
   annotation was attached to.
3. **Search for a replacement**.
   - `graph_find(name=<old short name>)` — often a rename keeps the
     short name and only changes the path.
   - `graph_find(qualname_prefix=<original prefix>)` — for moves that
     keep the leaf name.
   - If neither hits, `search(<original body text>)` may surface a
     candidate.
4. **Reattach if found**. `graph_reattach_orphan(annotation_id,
   new_node_id)` rewires the `ANNOTATES` edge to the replacement
   target.
5. **Delete if obsolete**. `graph_delete_annotation(annotation_id)`
   when the original meaning is gone — the artifact wasn't renamed,
   it was removed.
6. **Surface if unclear**. If you can't tell whether a candidate is
   the right replacement, leave the orphan in place and report it:
   "orphan annotation X (`<body excerpt>`) is unclear; please advise".

## Why this matters

Orphans are the KB's main quality risk. Left untriaged, they
accumulate as noise; reattached well, they preserve insight across
refactors. Make orphan triage part of any session that touches a
refactor or rename.
