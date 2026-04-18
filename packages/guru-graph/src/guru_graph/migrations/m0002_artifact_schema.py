"""m0002 — artifact-graph schema (schema_version 1 -> 2).

Adds uniqueness constraints for (:Document), (:Module), (:Class), (:Function),
(:Method), (:OpenApiSpec), (:OpenApiOperation), (:OpenApiSchema),
(:MarkdownSection), (:Annotation); adds indexes used by hot query paths.

Forward-only and idempotent: every step uses `IF NOT EXISTS` / `MERGE`, so
re-running the migration against a store that already contains the new
schema is a no-op. The migration registry (`run_pending_migrations`)
filters by version, so direct re-invocation of `apply()` against a higher
version store is still safe.
"""

from __future__ import annotations

from typing import Any

CYPHER_STEPS = [
    # Uniqueness constraints for artifact-graph nodes.
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT module_id_unique IF NOT EXISTS FOR (m:Module) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT class_id_unique IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT function_id_unique IF NOT EXISTS FOR (f:Function) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT method_id_unique IF NOT EXISTS FOR (m:Method) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT oas_spec_id_unique IF NOT EXISTS FOR (s:OpenApiSpec) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT oas_op_id_unique IF NOT EXISTS "
    "FOR (o:OpenApiOperation) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT oas_schema_id_unique IF NOT EXISTS "
    "FOR (s:OpenApiSchema) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT md_section_id_unique IF NOT EXISTS "
    "FOR (s:MarkdownSection) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT annotation_id_unique IF NOT EXISTS "
    "FOR (a:Annotation) REQUIRE a.id IS UNIQUE",
    # Indexes for hot query paths.
    "CREATE INDEX document_kb_name IF NOT EXISTS FOR (d:Document) ON (d.kb_name)",
    "CREATE INDEX document_language IF NOT EXISTS FOR (d:Document) ON (d.language)",
    "CREATE INDEX annotation_kind IF NOT EXISTS FOR (a:Annotation) ON (a.kind)",
    "CREATE INDEX annotation_author IF NOT EXISTS FOR (a:Annotation) ON (a.author)",
    "CREATE INDEX module_qualname IF NOT EXISTS FOR (m:Module) ON (m.qualname)",
    "CREATE INDEX class_qualname IF NOT EXISTS FOR (c:Class) ON (c.qualname)",
    "CREATE INDEX function_qualname IF NOT EXISTS FOR (f:Function) ON (f.qualname)",
    "CREATE INDEX method_qualname IF NOT EXISTS FOR (m:Method) ON (m.qualname)",
    # Bump (:_Meta {kind:'schema'}).schema_version to 2.
    "MERGE (m:_Meta {kind: 'schema'}) "
    "ON CREATE SET m.schema_version = 2, m.created_at = timestamp() "
    "ON MATCH SET m.schema_version = 2, m.updated_at = timestamp()",
]


def apply(backend: Any) -> None:
    for step in CYPHER_STEPS:
        backend.execute(step, {})
