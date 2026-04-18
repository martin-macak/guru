# KB graph model

## Node labels

- `Kb` — one per registered knowledge base.
- `Document` — one per indexed file (Markdown, Python source, OpenAPI YAML).
- `MarkdownSection` — heading-rooted section inside a `Document`.
- `Module` — a Python module.
- `Class` — a Python class.
- `Function` — a top-level function.
- `Method` (PR-7) — a function attached to a class.
- `OpenApiOperation` / `OpenApiSchema` (PR-8) — operations and schemas
  extracted from OpenAPI specs.
- `Annotation` — agent- or human-authored insight attached to any artifact.

## Identity

Every artifact id has the shape `<kb_name>::<path-or-qualname>`:

- `polyglot::docs/guide.md` — a doc.
- `polyglot::docs/guide.md#installation` — a section inside that doc.
- `polyglot::pkg.services.user.UserService` — a Python class.
- `polyglot::pkg.services.user.UserService.create` — a method.
- `polyglot::api/openapi.yaml::UserResource` — an OpenAPI schema.

Ids are stable across re-ingest as long as the path or fully-qualified name
does not change. Renames produce orphans — see `orphans.md`.

## Relationship types

- `CONTAINS` — hierarchical (`Document -> MarkdownSection`,
  `Module -> Class -> Method`). No `kind` property; the structure carries
  the meaning.
- `RELATES` — typed cross-artifact edges. Always carries a `kind`
  (`ArtifactLinkKind` — closed enum: `imports`, `inherits_from`,
  `implements`, `calls`, `references`, `documents`).
- `ANNOTATES` — every `Annotation` node points at exactly one target via
  `(:Annotation)-[:ANNOTATES]->(:Artifact)`.
- `LinkKind` (KB-level) — cross-KB edges between `Kb` nodes; a separate
  vocabulary from artifact `RELATES` and not relevant to per-artifact
  reasoning.

## Closed vs open properties

- Closed enums: `AnnotationKind` (`summary` / `gotcha` / `caveat` / `note`)
  and `ArtifactLinkKind` (above). Do not invent new values.
- Open dicts: `metadata` (artifact-side, parser-emitted) and `tags`
  (annotation-side, agent-emitted). Use these to extend without breaking
  the schema.

## Wire types

These are the typed shapes returned by the MCP tools and `/graph/*` HTTP
endpoints; keep them in mind when reading tool responses:

- `ArtifactNode` — `id`, `label`, `properties` (the parser-emitted dict —
  read `properties.get("kb_name")` / `properties.get("breadcrumb")` /
  `properties.get("qualname")` here), plus inline `annotations`,
  `links_out`, `links_in`.
- `AnnotationNode` — `id`, `target_id`, `target_label`, `kind`, `body`,
  `tags`, `author`, `created_at`, `updated_at`, `target_snapshot_json`.
- `ArtifactLink` — `from_id`, `to_id`, `kind`, `created_at`, `author`
  (nullable), `metadata`.
- `GraphEdgePayload` — generic edge shape (`from_id`, `to_id`,
  `rel_type`, `kind`, `properties`) used in `graph_neighbors` responses.
