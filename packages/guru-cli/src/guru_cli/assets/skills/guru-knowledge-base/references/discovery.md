# Discovery patterns

## The default order

1. `search(q)` first. Embeddings cover both doc-chunks and artifact-chunks,
   so a single vector query is the cheapest way to land near the right
   artifact. Each hit carries `metadata.artifact_qualname` — use it to
   pivot from text into structure.

2. `graph_find(name=…)` or `graph_find(qualname_prefix=…)` when you
   already know what to look for. Cheaper and more precise than search
   when you have a concrete identifier.

3. `graph_describe(node_id)` to load one node plus its annotations and
   adjacent links inline. One round-trip, full page; prefer this over
   chained `graph_neighbors` calls when you want context for a single
   artifact.

4. `graph_neighbors(node_id, depth=1, rel_type="RELATES", kind="calls")`
   for typed traversal. Filter by `rel_type` and `kind` aggressively —
   unfiltered neighborhoods explode on hub nodes.

## Last resort: `graph_query`

`graph_query(cypher=…)` is read-only and useful for one-off custom
traversals or aggregations the typed tools can't express.

Example — every Class with no Summary annotation:

```cypher
MATCH (c:Class)
WHERE NOT EXISTS {
  (c)<-[:ANNOTATES]-(a:Annotation {kind: "summary"})
}
RETURN c.id LIMIT 20
```

Default to the typed MCP tools (`graph_find` / `graph_describe` /
`graph_neighbors`) over `graph_query`. The typed return shapes give the
LLM more structure to reason about; raw Cypher returns untyped maps that
must be re-parsed. Reach for `graph_query` only when the typed tools
genuinely cannot express the query.
