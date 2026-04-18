# Write policy

## Dedup before every write

Always `graph_describe(target)` before `graph_annotate`. Inspect existing
annotations on that node:

- If an annotation with the same `kind` already exists and it's a
  `summary`, **update** it (summaries are replace-in-place).
- If it's a `gotcha`, `caveat`, or `note` and the existing entry already
  captures the insight, **skip** — don't duplicate.
- If the existing entry is partially right but stale, prefer
  `graph_update_annotation` over a second annotation.

Duplication erodes the KB's signal-to-noise ratio fast. A single canonical
note is worth more than three near-duplicates.

## Summary semantics

`graph_annotate(kind="summary", …)` REPLACES any existing summary on the
target — there is a one-summary-per-node invariant enforced server-side.
All other kinds APPEND, so a target may carry multiple `gotcha` /
`caveat` / `note` entries.

## Authorship

Every write stamps an `author` (`agent:claude-code`, `agent:<name>`, or
`user:<email>`). The stamp is preserved across sessions and surfaces in
`graph_describe` output and in orphan triage — use it to attribute and
to triage stale agent-written notes.

## Prefer link over note

If the insight is "X relates to Y", express it as a structural edge, not
as prose:

- `graph_link(from_id=X, to_id=Y, kind=…)` is queryable; downstream
  agents can traverse it.
- A `note` saying "this calls Y" is invisible to `graph_neighbors` and
  `graph_query`.

Use notes for behaviour, gotchas, and judgement calls. Use links for
relations.

## Closed vocabulary

`AnnotationKind` is a closed enum: `summary` / `gotcha` / `caveat` /
`note`. Do **not** invent new kinds (`"warning"`, `"todo"`, `"idea"`).
Extend the meaning with `tags` instead — `tags=["todo"]`, `tags=["idea",
"perf"]`. Tags are open and free-form; kinds are closed because the
server treats them differently (e.g. summary uniqueness).
