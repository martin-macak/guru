# Annotation kinds and tags

## Kind taxonomy

`AnnotationKind` is closed. Pick the one that matches:

- **`summary`** — single, replace-in-place. The canonical "what does this
  thing do?" answer for the target.
  *Example:* `UserService orchestrates user CRUD over the user table; all
  writes go through validate_user().`
- **`gotcha`** — append-only. Surprising behaviour, edge case, or
  foot-gun. Saves debugging time later.
  *Example:* `validate_user() silently lowercases the email before
  hashing — case-sensitive lookups will miss.`
- **`caveat`** — append-only. Constraint, limitation, or
  "don't do X here".
  *Example:* `Do not call from a request handler; opens its own DB
  connection and does not use the request session.`
- **`note`** — append-only. General observation that doesn't fit
  summary / gotcha / caveat.
  *Example:* `Originally written for the v1 schema; partially migrated
  to v2 — see PR #412 for the migration plan.`

## Tag taxonomy

Tags are free-form list-of-strings. Keep each tag short (one or two
words). Recommended families:

- **Behavior tags**: `perf`, `latency`, `concurrency`, `idempotent`.
- **Surface tags**: `api`, `internal`, `deprecated`, `experimental`.
- **Risk tags**: `fragile`, `security`, `breaking`.

Use tags to express the dimensions a `kind` cannot — e.g. a `gotcha`
tagged `["concurrency", "fragile"]` is more findable than an untagged
one.
