# `ArtifactLinkKind` — when each one applies

The closed vocabulary for `RELATES` edges between artifacts. Some are
emitted automatically by parsers; the rest are agent-authored.

## Parser-emitted (rarely added by hand)

- **`imports`** — module-level. `import X` or `from X import Y` becomes
  `(:Module from)-[:RELATES {kind:"imports"}]->(:Module to)`. The Python
  parser emits these for every resolvable import.
- **`inherits_from`** — class-level. `class B(A):` becomes
  `(:Class B)-[:RELATES {kind:"inherits_from"}]->(:Class A)`. Auto-emitted
  for resolved bases. Add manually only when the base is dynamically
  determined and the parser couldn't resolve it.
- **`calls`** — function-to-function. Auto-emitted by the Python parser
  when call sites are statically resolvable. Add manually for dynamic
  dispatch the parser missed (e.g. handler dicts, plugin registries).

## Agent-authored

- **`implements`** — use when a class implements a contract that the
  parser can't see — typically an OpenAPI operation, a Protocol, or an
  abstract interface defined in another KB.
  *Example:* you discover `pkg.services.user.UserService` implements the
  schema `api/openapi.yaml::UserResource`. Add:
  ```
  graph_link(
      from_id="polyglot::pkg.services.user.UserService",
      to_id="polyglot::api/openapi.yaml::UserResource",
      kind="implements",
  )
  ```
- **`references`** — weak: "this artifact mentions or depends on this
  other artifact" without a stronger relation. Use when nothing more
  specific applies.
  *Example:* a doc referencing an API endpoint without claiming to
  document it.
- **`documents`** — a document is the canonical docs for a code
  artifact.
  *Example:*
  ```
  graph_link(
      from_id="polyglot::docs/auth.md",
      to_id="polyglot::pkg.auth.AuthService",
      kind="documents",
  )
  ```

## Rule of thumb

Defer to the parser for `imports` / `inherits_from` / `calls`. Agent
links are for `implements` / `references` / `documents` — the cross-cuts
the parser cannot see.
