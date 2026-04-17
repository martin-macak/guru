"""m0001 — initial schema.

Creates:
  - constraint kb_name_unique (UNIQUE on :Kb.name)
  - index kb_updated_at (:Kb(updated_at))
  - (:_Meta {kind:'schema'}) singleton with schema_version=1

Note on _Meta singleton: Neo4j Community cannot enforce node-count
constraints. Discipline = always MERGE on {kind:'schema'}.
"""

from __future__ import annotations

from typing import Any

CYPHER_STEPS = [
    "CREATE CONSTRAINT kb_name_unique IF NOT EXISTS FOR (k:Kb) REQUIRE k.name IS UNIQUE",
    "CREATE INDEX kb_updated_at IF NOT EXISTS FOR (k:Kb) ON (k.updated_at)",
    "MERGE (m:_Meta {kind: 'schema'}) "
    "ON CREATE SET m.schema_version = 1, m.created_at = timestamp() "
    "ON MATCH SET m.schema_version = 1",
]


def apply(backend: Any) -> None:
    for step in CYPHER_STEPS:
        backend.execute(step, {})
