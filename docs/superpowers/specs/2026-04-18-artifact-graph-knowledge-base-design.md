# Artifact Graph Knowledge Base — Design

**Date:** 2026-04-18
**Status:** Draft
**Follows:** `2026-04-17-graph-plugin-design.md`, `2026-04-18-graph-readonly-cli-design.md`

---

## Problem

Guru's graph plugin (PR #35) ships the infrastructure — a `guru-graph` daemon, Neo4j backend, `(:Kb)` nodes, KB-to-KB links, migrations, protocol versioning, read-only CLI. What it does not ship: artifact modelling, an agent-facing surface, or any mechanism for the knowledge base to grow over time.

Today, agents can semantically search Markdown chunks and that is all. They cannot discover the classes, functions, or API operations inside a codebase. They cannot navigate structural relationships (who calls whom, what implements what, which spec references which schema). Most importantly, they cannot *store what they learn*: every gotcha an agent discovers, every cross-file connection it infers, every non-obvious behaviour it uncovers — all of that evaporates at session end, and the next session re-derives the same conclusions from scratch.

The vector index answers "what is this *like*?". Nothing today answers "what is this *connected to*?" or "what has a previous session *learned* about this?". Until both halves exist, "local-first knowledge-base manager" is really "local-first markdown search".

## Goals

1. **Extensible parser contract.** Ingestion learns to parse Python (tree-sitter), OpenAPI, and Markdown (retrofitted) into structured artifact nodes. The contract makes adding new languages — TS/JS, Go, Rust, JSON Schema, Protobuf, anything — a pure extension with zero core change.
2. **Per-file Document invariant.** Every indexed file produces **both** (a) ≥1 embedded chunk in LanceDB with rich metadata (file type, language, qualname), and (b) a `(:Document)` graph node plus any structural sub-artifact nodes — when the graph is enabled. Markdown-era behaviour still works unchanged when the graph is disabled.
3. **Agent-writable surface.** Ten new MCP tools spanning read / navigate / annotate / curate with a closed annotation vocabulary (`summary` / `gotcha` / `caveat` / `note`) + open `tags[]` array, and a closed artifact-link vocabulary.
4. **Durable annotations.** `(:Annotation)` nodes are first-class. They outlive the artifacts they described, surfaced as orphans for agent triage on refactor. Knowledge can only be lost with explicit agent consent.
5. **Hybrid search with no signature change.** `search()` transparently returns a mixed ranked list of doc-chunks and artifact-chunks; agents pivot into the graph via `metadata.artifact_qualname`. No new `hybrid_search()` tool.
6. **Shipped agent skill.** An `AGENTS.md`-compatible skill (one top-level `SKILL.md` + lazy `references/*.md`) teaches the agent the KB model and, critically, *why and when* to curate. Installed by `guru init`; updated safely by a new `guru update` command.
7. **Graph is strictly optional.** When the graph is disabled or unreachable, every guru operation continues unchanged. Graph failures never escape `graph_or_skip`.

## Non-Goals

- **No TypeScript / JavaScript / JSON-Schema parser in v1.** The extensible interface must land; those parsers arrive in follow-up specs.
- **No cross-project artifact deduplication.** Per-KB scoping only. Two projects each with `class User` produce two separate `:Class` nodes, each under its own `(:Kb)`.
- **No AST-similarity-based rename detection.** Orphan-preserving manual triage only.
- **No artifact embeddings in Neo4j's native vector index.** LanceDB remains the single vector store.
- **No freeform annotation kinds or link kinds.** Closed vocabularies; extension is a schema bump.
- **No orphan TTL auto-expiry.** Agent-driven pruning only.
- **No agent spoofing of authorship.** MCP stamps `author="agent:<client>"`; CLI stamps `author="user:<git-email>"`.
- **No MCP write tools beyond annotations + typed links.** Not a general graph-editing surface.
- **No Python call-site detection in v1.** Imports + inheritance ship; `CALLS` edges deferred.

---

## Constitution amendments (`ARCHITECTURE.md`)

Three new amendments, on top of the two already recorded for the graph plugin:

**A. Per-file Document invariant.**
> Every indexed file produces both a LanceDB chunk set and a `(:Document)` graph node when the graph is enabled. Graph-disabled mode discards graph facts; chunks still flow to LanceDB.

**B. Parser interface.**
> `DocumentParser` implementations emit a single `ParseResult` per file carrying chunks for LanceDB and (`Document`, sub-artifact nodes, edges) for the graph. Always-on dispatch by `supports()`; no per-parser config flag.

**C. MCP writes allowed for KB annotations and typed links.**
> MCP tools are read-only by default. Agent-writable knowledge-base operations — `graph_annotate`, `graph_link`, `graph_unlink`, `graph_delete_annotation`, `graph_reattach_orphan` — are the explicit exception. Any further write surface requires a constitution amendment.

**D. Graph is strictly optional — non-negotiable behavioural invariant.**
> Every graph-agnostic operation must work identically whether the graph is enabled, disabled, unreachable, or crashed. `search()`, `get_document()`, `list_documents()`, `get_section()`, `index_status()`, `federated_search()`, `list_peers()`, `guru index`, `guru search`, `guru status`, the background watcher, and the TUI: none change behaviour based on graph state. Graph state only affects graph-specific tools/commands.

---

## Architecture

### Component topology (unchanged from PR #35)

```
┌──────────── developer machine ────────────────────────────────┐
│                                                               │
│  proj-A ─┐                                                    │
│  proj-B ─┼─► guru-server (per project) ──┐                    │
│  proj-C ─┘                                │                   │
│                                           ▼                   │
│            (HTTP/UDS)             guru-graph daemon (one)     │
│                                            │                  │
│                                   (Bolt 127.0.0.1)            │
│                                            ▼                  │
│                                    Neo4j (JVM subprocess)     │
│                                                               │
│  guru-mcp / guru-cli ─► guru-server via .guru/guru.sock       │
│                    ─► guru-graph via graph.sock  (read-only   │
│                                                   via CLI;    │
│                                                   read+write  │
│                                                   via MCP →   │
│                                                   proxied by  │
│                                                   guru-server)│
└───────────────────────────────────────────────────────────────┘
```

No topology change. What changes is **what flows through it**.

### Ownership rules

- `guru-server` owns **per-project state**: LanceDB, ingestion, manifest, parser dispatch, embedding (Ollama).
- `guru-graph` owns **machine-wide graph state**: Neo4j subprocess, schema, all graph writes and reads.
- `guru-core` holds shared types + `GraphClient` (HTTP-over-UDS). Neither `guru-server` nor `guru-graph` imports the other.
- **(new)** `guru-cli` owns **skill distribution**: `guru init` / `guru update` copy the packaged skill tree into the user's repo.

### Indexing data flow (per file)

```
file.py / file.md / openapi.yaml
        │
        ▼
guru-server.indexer
        │
        ├─► ParserRegistry.dispatch(path) ─► ParseResult
        │       │
        │       ├── chunks: list[Chunk]       (with artifact_qualname metadata)
        │       ├── document:  GraphNode
        │       ├── nodes:     list[GraphNode]
        │       └── edges:     list[GraphEdge]
        │
        ├─► LanceDB: upsert all chunks (always, even when graph disabled)
        │      └── cache-aware embedding via existing EmbeddingCache
        │
        └─► graph_or_skip(
              GraphClient.submit_parse_result(kb, document, nodes, edges)
            )
                │
                ▼ (only when graph enabled AND reachable)
          guru-graph.ingest_service
                │
                ├─► diff against previous snapshot for this document
                ├─► upsert current nodes/edges
                └─► delete (previous − current); annotations on deleted
                    artifacts become orphans (edges break; nodes kept)
```

Properties:

- **LanceDB is primary; graph is augmentation.** A LanceDB write failure aborts the file's index; a graph failure is swallowed via `graph_or_skip`.
- **Reconciliation is per-file.** `guru-graph` tracks the previous artifact node set per `(:Document)` via a `snapshot_ids_json` property. Each submit computes the diff and applies it atomically in one transaction.
- **File deletion** is a normal case: indexer emits a "doc deleted" message; `guru-graph` removes the `:Document` + cascades to `:CONTAINS`-reachable artifacts. Annotations orphan.
- **Graph-disabled mode** short-circuits at `graph_or_skip`. `ParseResult.{document, nodes, edges}` are simply not transmitted.

### Query data flow (agent calls `search`)

```
agent ─► guru-mcp.search(q) ─► guru-server.search(q)
                                      │
                                      ▼
                            LanceDB similarity over ALL chunks
                                      │
                                      ▼
                     list[{content, score, metadata:{
                         kind, path, language, artifact_qualname?,
                         parent_document_id, kb_name, ...
                     }}]
```

No graph call on the happy path. The agent receives hybrid results and pivots — based on skill guidance — when needed:

```
agent ─► guru-mcp.graph_describe(qualname) ─► guru-server ─► guru-graph
```

**Routing decision.** MCP calls for graph operations go through `guru-server` (which proxies to `guru-graph` via `GraphClient`), not directly to `guru-graph`. Rationale: (1) `guru-server` already owns the MCP-relevant REST surface; (2) preserves the "clients never talk to `guru-graph` directly" invariant; (3) enables `guru-server` to enrich graph responses with project-scoped context; (4) centralises `graph_or_skip` + `author` stamping + read-only enforcement at one hop.

---

## Graph schema (schema_version = 2, migration m0002)

### Node labels

| Label | Purpose | Identity (`id` property) |
|---|---|---|
| `:Kb` (existing) | Per-project KB root | `name` (already unique) |
| `:Document` | One per indexed file | `<kb>::<relative_path>` |
| `:Module` | Python package/module | `<kb>::<qualname>` |
| `:Class` | Python class | `<kb>::<qualname>` |
| `:Function` | Top-level Python function | `<kb>::<qualname>` |
| `:Method` | Class method | `<kb>::<qualname>` |
| `:OpenApiSpec` | OpenAPI document | `<kb>::<relative_path>` |
| `:OpenApiOperation` | A single endpoint | `<kb>::<relative_path>::<METHOD> <path>` |
| `:OpenApiSchema` | Reusable schema under `components/schemas/` | `<kb>::<relative_path>::<name>` |
| `:MarkdownSection` | H2/H3 section | `<kb>::<relative_path>::<breadcrumb>` |
| `:Annotation` | Agent- or user-written durable note | UUID v4 (not kb-scoped — orphans survive KB deletion) |
| `:_Meta` (existing) | Schema/protocol metadata | singleton `{kind:'schema'}` |

All non-`:Kb` artifact labels carry `kb_name` as a denormalised property for fast per-KB queries without always traversing the `:Kb` root.

### Core per-node properties

```cypher
(:Document {
    id, kb_name, relative_path, absolute_path,
    language, file_type, content_hash, size_bytes,
    parser_name, created_at, updated_at,
    snapshot_ids_json           // JSON list of sub-artifact ids last emitted;
                                // used by guru-graph for diff reconciliation
})

(:Class {
    id, kb_name, qualname, name,
    docstring, is_abstract,
    line_start, line_end,
    signature_hash              // sha256(sorted-method-names + base-classes)
})

(:Function | :Method {
    id, kb_name, qualname, name, signature,
    docstring, is_async,
    is_static, is_classmethod,   // Method only; null on Function
    line_start, line_end, signature_hash
})

(:OpenApiOperation {
    id, kb_name, spec_id, method, path,
    operation_id, summary, description,
    tags_json, request_body_ref, response_refs_json
})

(:MarkdownSection {
    id, kb_name, breadcrumb, heading, level, chunk_level
})

(:Annotation {
    id,                         // UUID v4, stable for the lifetime of the annotation
    kind,                       // "summary" | "gotcha" | "caveat" | "note"
    body,                       // markdown
    tags_json,                  // open tags[]
    author,                     // "agent:claude-code" | "user:<email>"
    created_at, updated_at,
    target_snapshot_json        // frozen at creation: {target_id, target_kind, breadcrumb}
                                // enables orphan display after target deletion
})
```

### Relationship types (only four)

```cypher
// 1. Structural containment (hierarchy; no properties)
(:Kb)-[:CONTAINS]->(:Document)
(:Document)-[:CONTAINS]->(:Module | :OpenApiSpec | :MarkdownSection)
(:Module)-[:CONTAINS]->(:Class | :Function | :Module)
(:Class)-[:CONTAINS]->(:Method)
(:OpenApiSpec)-[:CONTAINS]->(:OpenApiOperation | :OpenApiSchema)
(:MarkdownSection)-[:CONTAINS]->(:MarkdownSection)        // nested sections

// 2. Semantic artifact-level relations (controlled vocabulary)
(:<Artifact>)-[:RELATES {kind, created_at, metadata_json, author?}]->(:<Artifact>)
    // kind ∈ ArtifactLinkKind

// 3. Annotations
(:Annotation)-[:ANNOTATES]->(:Kb | :Document | :Class | :Function | :Method
                             | :OpenApiSpec | :OpenApiOperation | :OpenApiSchema
                             | :MarkdownSection | :Module)

// 4. KB-to-KB links (unchanged from PR #35)
(:Kb)-[:LINKS {kind}]->(:Kb)        // kind ∈ LinkKind
```

### Controlled vocabularies

```python
class AnnotationKind(str, Enum):
    SUMMARY = "summary"     # replace-semantics, one per target
    GOTCHA  = "gotcha"      # append
    CAVEAT  = "caveat"      # append
    NOTE    = "note"        # append

class ArtifactLinkKind(str, Enum):
    IMPORTS       = "imports"         # Module→Module, Function→Module
    INHERITS_FROM = "inherits_from"   # Class→Class
    IMPLEMENTS    = "implements"      # Class→Class, Class→OpenApiSchema
    CALLS         = "calls"           # Function/Method→Function/Method
    REFERENCES    = "references"      # any→any, weak
    DOCUMENTS     = "documents"       # MarkdownSection/Document→any (explains)
```

Both enums are closed; adding a value is a MINOR protocol + schema bump, additive. `LinkKind` (Kb↔Kb) stays untouched from PR #35.

### Constraints and indexes

```cypher
CREATE CONSTRAINT document_id_unique      FOR (d:Document)          REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT module_id_unique        FOR (m:Module)            REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT class_id_unique         FOR (c:Class)             REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT function_id_unique      FOR (f:Function)          REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT method_id_unique        FOR (m:Method)            REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT oas_spec_id_unique      FOR (s:OpenApiSpec)       REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT oas_op_id_unique        FOR (o:OpenApiOperation)  REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT oas_schema_id_unique    FOR (s:OpenApiSchema)     REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT md_section_id_unique    FOR (s:MarkdownSection)   REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT annotation_id_unique    FOR (a:Annotation)        REQUIRE a.id IS UNIQUE;

CREATE INDEX document_kb_name    FOR (d:Document) ON (d.kb_name);
CREATE INDEX document_language   FOR (d:Document) ON (d.language);
CREATE INDEX annotation_kind     FOR (a:Annotation) ON (a.kind);
CREATE INDEX annotation_author   FOR (a:Annotation) ON (a.author);
CREATE INDEX artifact_qualname   FOR (n:Module|Class|Function|Method) ON (n.qualname);
```

### Migration `m0002_artifact_schema.py`

1. Create all new labels' uniqueness constraints.
2. Create all new indexes.
3. Backfill: for every existing `(:Kb)`, if a corresponding `guru-server` is running and reachable, trigger a full re-index via `POST /reindex`. Otherwise the next normal re-index populates artifacts.
4. Bump `:_Meta.schema_version` to 2 and protocol version to `1.1.0` (MINOR).

Forward-only, idempotent (checks `schema_version` before acting). No down-migration.

### Orphan mechanics in one place

When a `(:Document)` or sub-artifact is deleted during reconciliation:

1. Fetch all `(:Annotation)-[:ANNOTATES]->(target)` inbound edges.
2. Delete the `:ANNOTATES` edges (not the `:Annotation` nodes).
3. Delete the target node.
4. Orphan annotations are found by `MATCH (a:Annotation) WHERE NOT (a)-[:ANNOTATES]->() RETURN a`. The `target_snapshot_json` property preserves enough context for the agent to reattach.

---

## Parser contract + ingestion + LanceDB

### The interface (`guru-server/ingestion/base.py`)

```python
@dataclass
class GraphNode:
    node_id: str                # stable within document; parser composes from kb/path/qualname
    label: str                  # "Document" | "Module" | "Class" | ...
    properties: dict[str, Any]

@dataclass
class GraphEdge:
    from_id: str
    to_id: str
    rel_type: Literal["CONTAINS", "RELATES"]
    kind: str | None = None     # ArtifactLinkKind.value when rel_type == "RELATES"
    properties: dict[str, Any] = field(default_factory=dict)

@dataclass
class Chunk:                    # extends today's Chunk
    content: str
    file_path: str
    header_breadcrumb: str
    chunk_level: int
    frontmatter: dict[str, Any] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    parent_chunk_id: str | None = None
    chunk_id: str | None = None
    content_type: str = "text"
    # NEW ↓
    kind: str = "text"                        # "text" | "code" | "openapi_operation" | "openapi_schema" | "markdown_section"
    language: str | None = None
    artifact_qualname: str | None = None
    parent_document_id: str | None = None     # always set (kb-scoped)

@dataclass
class ParseResult:
    chunks: list[Chunk]
    document: GraphNode                        # always exactly one, even for markdown
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

class DocumentParser(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...                 # "markdown" | "python" | "openapi"

    @abstractmethod
    def supports(self, file_path: Path) -> bool: ...

    @abstractmethod
    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult: ...
```

### The registry

```python
class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[DocumentParser] = []

    def register(self, parser: DocumentParser) -> None: ...

    def dispatch(self, file_path: Path) -> DocumentParser | None:
        for p in self._parsers:                # order = registration order
            if p.supports(file_path):
                return p
        return None
```

Default registrations (at `guru-server` startup):

```python
registry.register(MarkdownParser())
registry.register(PythonParser())
registry.register(OpenApiParser())
```

Adding a parser later is one `register()` call. No core change.

### Ingestion reconciliation

Per file on each indexing run:

1. Dispatch to parser → `ParseResult`.
2. **LanceDB** (primary): `store.delete_file(rel_path); store.add_chunks(chunks, vectors)` exactly as today. Embedding uses the existing cache.
3. **Graph** (augmentation, wrapped in `graph_or_skip`):
   ```python
   await graph_or_skip(
       client.submit_parse_result(
           kb_name=kb,
           document=result.document,
           nodes=result.nodes,
           edges=result.edges,
       ),
       feature="ingest_artifacts",
   )
   ```

Server-side `submit_parse_result` pseudo-code:

```text
BEGIN tx
  prev := MATCH (d:Document {id: document.id}) RETURN d.snapshot_ids_json
  prev_ids := json.loads(prev or "[]")
  current_ids := [n.node_id for n in nodes]

  to_delete := prev_ids − current_ids
  to_upsert := nodes + document

  FOR each node_id in to_delete:                      // orphan-preserving delete
    MATCH (n {id: node_id})<-[r:ANNOTATES]-(a:Annotation)
      DELETE r                                         // edge only; annotation survives
    MATCH (n {id: node_id}) DETACH DELETE n

  FOR each n in to_upsert:
    MERGE (x {id: n.node_id}) SET x += n.properties, x:<n.label>

  MATCH (d:Document {id: document.id})-[:CONTAINS*1..]->(child)
  MATCH (child)-[r:RELATES]->() DELETE r                // replace outbound semantic edges

  FOR each e in edges:
    MATCH (from {id: e.from_id}), (to {id: e.to_id})
    CREATE (from)-[:<e.rel_type> {kind: e.kind, ...e.properties}]->(to)

  UPDATE (:Document {id: document.id}).snapshot_ids_json := json.dumps(current_ids)
COMMIT
```

Concurrency: one transaction per file. Multiple files from the same indexing run are serialised by `guru-server`'s single-threaded indexer. Multiple `guru-server` instances (different projects) can submit concurrently; Neo4j handles transaction isolation.

### LanceDB metadata schema additions

New columns on the chunks table:

```
kind                  text    # "text" | "code" | "openapi_operation" | "openapi_schema" | "markdown_section"
language              text    # "python" | "markdown" | "openapi" | ...
artifact_qualname     text    # nullable; pointer into the graph node id
parent_document_id    text    # always set; "<kb>::<relative_path>"
```

Schema evolution on first load (LanceDB supports additive columns); implementation plan includes a verification step on existing `.guru/` stores.

### Per-parser notes

**Markdown** (existing, extended):
- `document.node_id = <kb>::<relative_path>`; `document.properties.language = "markdown"`, `file_type = "doc"`.
- Emits `(:MarkdownSection)` per section with hierarchical `:CONTAINS` edges. Existing chunks gain `kind="markdown_section"`, `artifact_qualname = <section id>`.

**Python** (new, tree-sitter-python):
- qualname: `<module-dotted-path>[.<Class>[.<method>]]`. Module path derived from relative file path after walking `__init__.py` boundaries.
- Emits `(:Module)` per package/module, `(:Class)`, `(:Function)`, `(:Method)`.
- Semantic edges:
  - `import X` / `from X import Y` → `(:Module)-[:RELATES {kind:"imports"}]->(:Module)`.
  - `class B(A):` → `(:Class B)-[:RELATES {kind:"inherits_from"}]->(:Class A)`. Unresolved refs produce placeholder nodes outside containment.
  - Call-site detection deferred.
- Chunk per top-level symbol: `{signature}\n\n{docstring}\n\n{body-head ≤ 800 tokens}`. Methods chunked with their class docstring prepended.

**OpenAPI** (new):
- Accepts `*.yaml`, `*.yml`, `*.json` where the root contains `openapi: 3.x` (sniffed in `supports()`).
- Emits `(:OpenApiSpec)`, one `(:OpenApiOperation)` per `paths.*.<method>`, one `(:OpenApiSchema)` per `components.schemas.*`.
- `$ref` to a local schema → `(:OpenApiOperation)-[:RELATES {kind:"references"}]->(:OpenApiSchema)`.
- Cross-file `$ref` resolved relative to the spec's directory. Unresolved targets produce placeholder nodes flagged `resolved=false`.
- Circular `$ref` safe (visited set).
- `oneOf` / `anyOf` / `allOf` collapsed to a single schema with `metadata.shape` preserved.
- Malformed specs: single `:OpenApiSpec` node with `Document.properties.valid=false` and the parse error. No sub-artifacts.
- Chunks: one per operation (`"{METHOD} {path}\n\nsummary: ...\n\ndescription: ..."`); one per schema.

---

## MCP, REST, and CLI surface

### The 10 new MCP tools

All live in `packages/guru-mcp/src/guru_mcp/server.py`. Each is a thin wrapper over `guru-server`'s `/graph/*` REST endpoints. Each returns a structured dict; on `graph_unavailable` they return `{"error": "graph_unavailable", "detail": "..."}`. Authorship is stamped by `guru-server` based on the MCP client identity from the FastMCP handshake; no agent-supplied `author` is accepted.

```python
@mcp.tool()
async def graph_describe(node_id: str) -> dict: ...
    """Fetch a graph node with properties, all annotations, and direct links."""

@mcp.tool()
async def graph_neighbors(
    node_id: str,
    direction: Literal["in", "out", "both"] = "both",
    rel_type: Literal["CONTAINS", "RELATES", "both"] = "both",
    kind: str | None = None,
    depth: int = 1,
    limit: int = 50,
) -> dict: ...

@mcp.tool()
async def graph_find(
    *,
    name: str | None = None,
    qualname_prefix: str | None = None,
    kind: str | None = None,       # node label
    tag: str | None = None,
    kb_name: str | None = None,    # defaults to current project's KB
    limit: int = 50,
) -> dict: ...

@mcp.tool()
async def graph_annotate(
    node_id: str,
    kind: Literal["summary", "gotcha", "caveat", "note"],
    body: str,
    tags: list[str] | None = None,
) -> dict: ...
    """Write an annotation. kind='summary' replaces any existing summary on
    this node; the others append."""

@mcp.tool()
async def graph_delete_annotation(annotation_id: str) -> dict: ...

@mcp.tool()
async def graph_link(
    from_id: str,
    to_id: str,
    kind: Literal["imports","inherits_from","implements","calls","references","documents"],
    metadata: dict | None = None,
) -> dict: ...

@mcp.tool()
async def graph_unlink(from_id: str, to_id: str, kind: str) -> dict: ...

@mcp.tool()
async def graph_orphans(limit: int = 50) -> dict: ...

@mcp.tool()
async def graph_reattach_orphan(annotation_id: str, new_node_id: str) -> dict: ...

@mcp.tool()
async def graph_query(cypher: str, params: dict | None = None) -> dict: ...
    """Read-only Cypher escape hatch. read_only=True is forced server-side."""
```

Existing `search()` now transparently returns artifact chunks mixed with doc chunks — no signature change.

### REST endpoint mapping (guru-server → guru-graph)

| MCP tool | guru-server route | guru-graph route |
|---|---|---|
| `graph_describe` | `GET /graph/describe/{node_id}` | `GET /artifacts/{id}` |
| `graph_neighbors` | `GET /graph/neighbors/{node_id}` | `GET /artifacts/{id}/neighbors` |
| `graph_find` | `POST /graph/find` | `POST /artifacts/find` |
| `graph_annotate` | `POST /graph/annotations` | `POST /annotations` |
| `graph_delete_annotation` | `DELETE /graph/annotations/{id}` | `DELETE /annotations/{id}` |
| `graph_link` | `POST /graph/links` | `POST /relates` |
| `graph_unlink` | `DELETE /graph/links` | `DELETE /relates` |
| `graph_orphans` | `GET /graph/orphans` | `GET /annotations/orphans` |
| `graph_reattach_orphan` | `POST /graph/orphans/{id}/reattach` | `POST /annotations/{id}/reattach` |
| `graph_query` | `POST /graph/query` | `POST /query` (read-only forced) |

Plus, for the indexer → graph ingestion path (not exposed to MCP):

```
POST   /ingest/parse-result      {kb_name, document, nodes, edges}
DELETE /ingest/documents/{doc_id}
```

### CLI extensions (read-only, per existing invariant)

```
guru graph describe    <node_id>                         [--json]
guru graph neighbors   <node_id> [--direction in|out|both] [--depth N] [--json]
guru graph find        [--name TEXT] [--qualname-prefix TEXT]
                       [--kind TEXT] [--tag TEXT] [--limit N] [--json]
guru graph annotations <node_id> [--kind TEXT]           [--json]
guru graph orphans     [--limit N]                       [--json]
```

**No** CLI commands for `annotate` / `link` / `unlink` / `delete_annotation` / `reattach_orphan`. Writes are agent-only, enforced by two new safety unit tests in `test_graph_cli_safety.py`.

### Error contract (graph-specific tools/commands)

| State | MCP return | CLI exit | CLI stderr |
|---|---|---|---|
| Graph disabled by config | `{"status":"graph_disabled","hint":"set graph.enabled=true in config"}` | **0** | — on stdout: `graph is disabled` |
| Graph enabled, daemon unreachable / 503 / 426 / stale socket | `{"error":"graph_unavailable","detail":"..."}` | **1** | `daemon: unreachable (<reason>)` |
| Node/annotation/link not found | `{"error":"not_found","detail":"..."}` | **1** | `<id> not found` |
| Validation failure (unknown kind, malformed cypher) | `{"error":"invalid_request","detail":"..."}` | **2** | `<detail>` |
| Happy path | typed payload | **0** | — |
| Unexpected (bug) | exception | non-zero | stack trace |

"Graph disabled" uses `status`, not `error` — a valid configuration, not a failure. Scripts + agents distinguish trivially: `"status" in resp and resp["status"] == "graph_disabled"`.

---

## Agent skill — content, distribution, lifecycle

### Directory layout (in the user's repo, after `guru init`)

```
.claude/skills/guru-knowledge-base/
├── SKILL.md                        # top-level, ≤400 words
├── references/
│   ├── model.md                    # schema + identity rules
│   ├── discovery.md                # search + graph_find + graph_describe + graph_neighbors
│   ├── curation.md                 # when to annotate, dedup, orphan triage
│   ├── annotation-shape.md         # kinds vs tags, summary vs append
│   ├── linking-patterns.md         # ArtifactLinkKind vocabulary + when each applies
│   └── orphans.md                  # triage workflow after refactors
└── MANIFEST.json                   # { "guru_version": "x.y.z", "files": {path: sha256, ...} }

.agents/skills/guru-knowledge-base  -> ../../.claude/skills/guru-knowledge-base   (symlink)
```

Canonical source in the guru wheel: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/`. Included via hatchling's `[tool.hatch.build.targets.wheel.force-include]`.

### SKILL.md content commitments

Frontmatter (locked):

```yaml
---
name: guru-knowledge-base
description: >
  Use when working in a guru-managed codebase — when discovering, investigating,
  or drawing conclusions about APIs, classes, functions, or cross-file relationships.
  Establishes how to search, navigate, annotate, and curate the project's durable
  knowledge base so derived insight compounds across sessions rather than being
  re-derived each time.
---
```

Body structure (≤400 words):

1. **What this is** — The guru KB = LanceDB vector index (always on) + optional Neo4j-backed structural graph. Every indexed file is a `(:Document)` with sub-artifacts; annotations are durable first-class nodes.
2. **Why this matters** — Derived insight is the scarcest artifact in software engineering and the most wasted. Every gotcha, every cross-file connection, every behavioural quirk — without the KB, those evaporate at session end. Curating the KB turns one session's work into every future session's starting context. The KB is a co-author, not a search index.
3. **How to discover** — `search(q)` returns both doc-chunks and artifact-chunks; pivot via `metadata.artifact_qualname`. `graph_find` for structural lookups. `graph_describe` for the whole page on one node. `graph_neighbors` for traversal. Defer `graph_query` to `references/discovery.md` — it is last-resort.
4. **When to write** — After a non-trivial investigation. When a user correction teaches something non-obvious. When you identify a cross-artifact relation the parser did not catch. Before writing, `graph_describe` the target to check if an annotation already exists — dedup or update.
5. **When NOT to write** — Do not re-state what the code already says. Do not summarise trivially. Do not store ephemeral or session-specific thoughts. Do not invent new kinds; use `kind + tags`.
6. **Curation loop** — When `graph_orphans()` returns items, triage: `graph_reattach_orphan` if the refactor renamed something, `graph_delete_annotation` if obsolete, leave untouched only if human decision is needed.
7. **Graph disabled** — If any `graph_*` tool returns `{"status":"graph_disabled"}`, this project is vector-only — use `search()` and stop.
8. **Deep dives** — Pointers to `references/*.md`.

### `references/*.md` — purpose & size budget

| File | Purpose | Loaded when |
|---|---|---|
| `model.md` (~300 w) | Full schema: node labels, identity rules, four relationship types, closed vs open properties. | Agent needs a label filter. |
| `discovery.md` (~250 w) | Navigation patterns + one Cypher recipe for when `graph_query` is genuinely needed. | Structural navigation beyond `graph_describe`. |
| `curation.md` (~300 w) | Write policy: dedup check, summary-replaces-append semantics, authorship, prefer-link-over-note. | About to call `graph_annotate` / `graph_link`. |
| `annotation-shape.md` (~200 w) | `summary`/`gotcha`/`caveat`/`note` distinctions with canonical examples; good tag taxonomies. | Agent unsure of kind. |
| `linking-patterns.md` (~250 w) | When to use each `ArtifactLinkKind`; worked examples. | About to call `graph_link`. |
| `orphans.md` (~200 w) | Triage recipe: list, group, candidate search, reattach/prune. | `graph_orphans` returns non-empty. |

Total skill token budget: ~400 w top + references lazy-loaded per task.

### Distribution & lifecycle

**Installation — `guru init` (extended):**

```python
def init(...) -> None:
    # existing: create .guru/, write guru.json
    _install_skills(project_root=cwd, scope="project")

def _install_skills(project_root: Path, scope: Literal["project","user"]) -> None:
    dest = project_root / ".claude" / "skills" / "guru-knowledge-base"
    src  = importlib.resources.files("guru_cli.assets.skills.guru-knowledge-base")
    _copy_tree(src, dest)
    _symlink(project_root / ".agents" / "skills" / "guru-knowledge-base",
             target=dest)
    _write_manifest(dest, guru_version=__version__)
```

Prints: `installed skill: .claude/skills/guru-knowledge-base (edit to customize)`.

**Update — `guru update` (new command):**

```
guru update [--skills] [--force] [--dry-run]
```

Compares shipped file hashes against `.claude/skills/guru-knowledge-base/MANIFEST.json`:

- Shipped file unchanged, user's copy unchanged → no-op.
- Shipped file changed, user's copy matches the old manifest hash → safe overwrite, update manifest.
- Shipped file changed, user's copy diverges from old manifest (user customised) → **skip**; print `skill/<file>: modified by you, left alone (use --force to overwrite; --dry-run for diff)`.
- `--force` overwrites regardless; backs up the custom copy to `<path>.bak.<timestamp>`.
- `--dry-run` prints actions without writing.

Idempotent. `guru update` twice in a row is a no-op.

**Windows**: symlink creation requires elevated permissions on older Windows versions. On Windows, the fallback is to mirror the `.claude/skills/…` tree under `.agents/skills/…` as a regular directory copy, with a warning printed. The `guru update` command mirrors both locations.

### Non-commitments

- No online skill updates. Skill changes ship with guru package upgrades.
- No per-agent variant (Claude Code vs Gemini vs Copilot). The `.agents/skills/` symlink covers all frameworks reading from that path.
- No skill auto-activation tuning beyond the frontmatter `description`.

---

## Housekeeping contracts

- **Annotation provenance.** Every `(:Annotation)` carries `author: str` (e.g. `"agent:claude-code"` or `"user:<git-email>"`) and `created_at`. The MCP server stamps `author="agent:<client-name>"` automatically from MCP client introspection; CLI writes stamp `"user:<git-config-user.email>"`. No spoofing from MCP.
- **Orphan TTL.** Forever in v1. Agent-driven pruning via `graph_delete_annotation` is the only cleanup path. A `guru graph orphans --older-than 30d` CLI subcommand can be added later.
- **Graph-disabled MCP behaviour.** Graph tools return `{"status":"graph_disabled"}` (not `error`). Matches the existing `graph_or_skip` philosophy.
- **Ingestion async boundary.** Graph writes during indexing go through `graph_or_skip`. Indexing never blocks on graph I/O. Embeddings to LanceDB remain synchronous (primary).
- **ArtifactLinkKind vocabulary.** Closed enum. Parser-emitted and agent-writable use the same vocabulary. New kinds require a MINOR schema bump.

---

## Testing strategy

### Tier 1 — Unit tests (per package)

| File | Coverage |
|---|---|
| `packages/guru-server/tests/unit/test_parser_registry.py` | Dispatch order, first-match-wins, `supports()` contract, unknown extension returns None. |
| `packages/guru-server/tests/unit/test_python_parser.py` | AST → qualname derivation; classes/methods/functions; `import`/`from` edge extraction; inheritance edge extraction; nested classes; decorators; async functions; `__init__.py` module promotion; subpackages. |
| `packages/guru-server/tests/unit/test_openapi_parser.py` | YAML + JSON; OpenAPI 3.0 + 3.1; operations per path/method; schemas under `components/schemas/`; local `$ref`; cross-file `$ref`; circular `$ref`; `oneOf`/`anyOf`/`allOf`; missing `components`. |
| `packages/guru-server/tests/unit/test_markdown_parser.py` | Existing tests extended: parser emits `(:Document)` + `(:MarkdownSection)` with `:CONTAINS`; chunks unchanged. |
| `packages/guru-server/tests/unit/test_reconciliation.py` | Diff algorithm on FakeBackend: previous vs current → delete/upsert; orphan creation; idempotent on replay. |
| `packages/guru-server/tests/unit/test_graph_integration.py` | `submit_parse_result` wrapped in `graph_or_skip`: `GraphUnavailable` → indexing completes, LanceDB state correct. |
| `packages/guru-graph/tests/unit/test_artifact_service.py` | Upsert Document → attach nodes → diff delete → orphan; reattach; prune. FakeBackend. |
| `packages/guru-graph/tests/unit/test_annotation_service.py` | Summary replace, gotcha/caveat/note append, author stamping from request context, orphan identification query. |
| `packages/guru-graph/tests/unit/test_m0002_migration.py` | v1 → v2: constraints + indexes idempotent; refuses downgrade. |
| `packages/guru-mcp/tests/unit/test_graph_tools.py` | Ten tools: kwargs pass through; `graph_unavailable` returns dict; author stamping on writes; `graph_query` always sends `read_only=true`. |
| `packages/guru-cli/tests/unit/test_init_skill_install.py` | `guru init` materialises skill tree + symlink; MANIFEST hashes correct. |
| `packages/guru-cli/tests/unit/test_update_skill.py` | no-op / overwrite / drift-skip / `--force` / `--dry-run`; backup on force; manifest refresh. |
| `packages/guru-cli/tests/unit/test_graph_cli_safety.py` | Asserts write tools absent from CLI; graph-disabled CLI exits 0. |

### Tier 2 — Integration tests

| File | Coverage |
|---|---|
| `packages/guru-server/tests/integration/test_ingest_full_flow.py` | Fixture with 1 Python + 1 Markdown + 1 OpenAPI. Graph disabled → LanceDB only. Graph enabled (FakeBackend via GraphClient stub) → both LanceDB + graph populated. |
| `packages/guru-graph/tests/integration/test_routes_fakebackend.py` | FastAPI TestClient over new `/artifacts/*`, `/annotations/*`, `/relates` routes; 404 / 422 / read-only enforcement. |
| `packages/guru-graph/tests/integration/test_neo4j_artifacts.py` | `@real_neo4j`. Real m0002 migration. Upsert Document/Class/Method; annotate; orphan after delete; reattach; round-trip. |
| `tests/test_cross_package_graph.py` | guru-mcp → guru-server → guru-graph (FakeBackend in-process) via real HTTP-over-UDS. Asserts `search()` returns artifact chunks when enabled; identical minus `artifact_qualname` when disabled. |

### Tier 3 — BDD e2e features (tests/e2e/features/)

Ten feature files. Every scenario below is a hard acceptance criterion; missing scenarios = incomplete implementation. `@real_neo4j` / `@real_ollama` tags follow the existing convention.

#### `artifact_indexing.feature`

```gherkin
Feature: Artifact graph indexing for Python, OpenAPI, and Markdown

  Background:
    Given a fixture project "polyglot" with:
      | path                          | kind     |
      | src/pkg/__init__.py           | python   |
      | src/pkg/auth.py               | python   |
      | src/pkg/services/user.py      | python   |
      | docs/guide.md                 | markdown |
      | api/openapi.yaml              | openapi  |

  @real_neo4j @real_ollama
  Scenario: Fresh index populates LanceDB and graph in lockstep
    Given graph is enabled
    When I run `guru index`
    Then LanceDB contains chunks for every file, each with kind/language metadata
    And every indexed file has a corresponding (:Document) node in the graph
    And pkg.auth has a (:Module) node containing its classes and functions
    And every (:Class) in pkg.services.user has its (:Method) children via :CONTAINS
    And api/openapi.yaml has one (:OpenApiSpec) + N (:OpenApiOperation) + M (:OpenApiSchema)
    And docs/guide.md has (:MarkdownSection) nodes matching its H2/H3 headings

  @real_neo4j
  Scenario: Parser emits structural imports and inheritance
    When I run `guru index`
    Then (:Module "pkg.auth")-[:RELATES {kind:"imports"}]->(:Module "pkg.services.user") exists
    And for every `class Derived(Base):`, (:Class)-[:RELATES {kind:"inherits_from"}]-> exists

  @real_neo4j
  Scenario: Re-indexing an unchanged file is a no-op in the graph
    Given `guru index` has run once
    When I record the (:Document) updated_at timestamps
    And I run `guru index` again without modifying files
    Then every (:Document).updated_at is unchanged
    And no transactions were committed to Neo4j beyond reads

  @real_neo4j
  Scenario: Editing a file adds/removes artifacts via diff reconciliation
    Given `guru index` has run once
    When I add a new method `logout` to UserService in pkg.services.user
    And I remove the method `deprecated_fn` from pkg.services.user
    And I run `guru index`
    Then (:Method "pkg.services.user.UserService.logout") exists
    And (:Method "pkg.services.user.UserService.deprecated_fn") does not exist
    And no other (:Method) node under UserService was touched

  @real_neo4j
  Scenario: Deleting a file cascades and creates orphans
    Given an annotation was written on (:Function "pkg.auth.hash_password")
    When the file src/pkg/auth.py is deleted
    And I run `guru index`
    Then (:Document "polyglot::src/pkg/auth.py") does not exist
    And no (:Module "pkg.auth") exists
    And the annotation is now an orphan (no outgoing :ANNOTATES edge)
    And graph_orphans() returns it with target_snapshot_json pointing at "pkg.auth.hash_password"

  Scenario: Extensible parser registration works without core change
    Given a test parser "ProtobufParser" is registered at startup
    And the fixture has a file api/schema.proto
    When I run `guru index`
    Then the ProtobufParser was dispatched for api/schema.proto
    And the emitted (:Document) + custom labels are present in the graph
```

#### `hybrid_search.feature`

```gherkin
Feature: Hybrid vector + graph search via a single search() call

  @real_ollama
  Scenario: search() returns a mix of doc-chunks and artifact-chunks
    Given fixture project "polyglot" is indexed with graph enabled
    When I call search("user authentication") via MCP
    Then results include at least one chunk with metadata.kind = "markdown_section"
    And results include at least one chunk with metadata.kind = "code" and metadata.artifact_qualname set
    And every result has metadata.parent_document_id set

  @real_ollama @real_neo4j
  Scenario: Agent pivots from a vector hit into the graph
    Given the top search hit has metadata.artifact_qualname = "polyglot::pkg.services.user.UserService"
    When the agent calls graph_describe("polyglot::pkg.services.user.UserService")
    Then the response includes the class's methods, inheritance, and any existing annotations

  @real_ollama
  Scenario: Graph disabled — search() still returns mixed chunks
    Given graph is disabled
    When I re-index the fixture from scratch
    And I call search("user authentication")
    Then artifact chunks are still present in results
    But no graph nodes exist
    And graph_describe() returns {"status":"graph_disabled"}
```

#### `annotations_and_curation.feature`

```gherkin
Feature: Agent-writable annotations with closed vocabulary + open tags

  Background:
    Given fixture project "polyglot" is indexed with graph enabled
    And a Claude-Code-style MCP session is connected

  @real_neo4j
  Scenario: Agent writes a summary (replace-semantics)
    When agent calls graph_annotate(node_id="…UserService", kind="summary", body="Owns user auth lifecycle.")
    Then graph_describe("…UserService").annotations.summary.body == "Owns user auth lifecycle."
    And annotation.author == "agent:claude-code"
    When agent calls graph_annotate(…, kind="summary", body="Orchestrates login + session.")
    Then only one summary annotation exists on …UserService
    And its body == "Orchestrates login + session."

  @real_neo4j
  Scenario: Gotcha append-semantics preserve history
    When agent writes three gotchas on …UserService with different tags
    Then graph_describe returns all three, each its own :Annotation node
    And filtering by tag returns the right subset

  @real_neo4j
  Scenario: User vs agent authorship is preserved
    When the HTTP API writes an annotation with author="user:me@example.com"
    Then the annotation is distinguishable at query time via author prefix

  @real_neo4j
  Scenario: Agent dedup workflow before writing
    Given a gotcha "Retries double-invoke on timeout" already exists on …UserService
    When the agent calls graph_describe(…UserService) before writing
    Then it sees the existing gotcha
    And the skill guidance instructs to update rather than re-add

  Scenario: Attempting to invent a new annotation kind is rejected
    When agent calls graph_annotate(kind="warning", ...)
    Then the MCP tool returns {"error":"invalid_request","detail":"kind must be one of summary/gotcha/caveat/note"}
```

#### `orphan_triage.feature`

```gherkin
Feature: Annotations survive refactors as orphans, agent triages

  Background:
    Given fixture "polyglot" is indexed
    And an agent has written a summary + two gotchas on (:Class "…UserService")

  @real_neo4j
  Scenario: Rename produces three orphans; agent reattaches
    When a developer renames UserService to AccountService
    And I run `guru index`
    Then graph_describe("…UserService") returns {"error":"not_found"}
    And graph_orphans() returns three annotations
    And each orphan.target_snapshot_json contains {"target_id":"…UserService", ...}
    When agent calls graph_reattach_orphan(annotation_id, new_node_id="…AccountService")
    Then the annotation now has :ANNOTATES -> AccountService
    And it is no longer returned by graph_orphans()

  @real_neo4j
  Scenario: Obsolete orphan is pruned
    When an orphan summary refers to a deleted experiment class
    And agent calls graph_delete_annotation(orphan_id)
    Then graph_orphans() no longer contains it
    And the annotation node is gone
```

#### `artifact_links.feature`

```gherkin
Feature: Parser-emitted + agent-written typed links

  @real_neo4j
  Scenario: Parser emits imports and inheritance from Python source
    Given fixture "polyglot" is indexed
    Then edges of kind "imports" and "inherits_from" are present per the parser rules

  @real_neo4j
  Scenario: Agent manually links a class to its OpenAPI contract
    When agent calls graph_link(
            from_id="polyglot::pkg.services.user.UserService",
            to_id="polyglot::api/openapi.yaml::UserResource",
            kind="implements",
            metadata={"note":"discovered by inspection"})
    Then the edge exists with author=agent:claude-code
    When agent calls graph_unlink(... same ..., kind="implements")
    Then the edge is gone

  Scenario: Unknown link kind is rejected
    When agent calls graph_link(kind="invented_kind", ...)
    Then response is {"error":"invalid_request","detail":"kind must be one of imports/inherits_from/implements/calls/references/documents"}
```

#### `graph_optional.feature`

```gherkin
Feature: Graph is strictly optional — guru operates identically without it

  Scenario: Full guru lifecycle with graph disabled
    Given graph is disabled by config
    When I run `guru init`, `guru index`, `guru search "foo"`, `guru status`
    Then every command exits 0
    And `guru status` reports graph_reachable=false
    And search returns results from LanceDB as usual
    And no guru-graph daemon was spawned

  Scenario: Graph MCP tools return status, not error, when disabled
    Given graph is disabled
    When MCP calls graph_describe, graph_find, graph_orphans, graph_annotate
    Then each returns {"status":"graph_disabled", ...}
    And none raise exceptions

  Scenario: CLI graph commands exit 0 when graph disabled
    Given graph is disabled
    When I run `guru graph orphans`
    Then exit code is 0
    And stdout contains "graph is disabled"

  @real_neo4j
  Scenario: Daemon crash mid-indexing — guru-server completes; graph data is partial
    Given graph is enabled and `guru index` is running
    When I SIGKILL guru-graph after the 3rd file is indexed
    Then `guru index` still completes
    And LanceDB contains every chunk
    And the graph contains what was submitted before the kill
    And `guru status` reports graph_reachable=false afterwards
    When I re-run `guru index` after daemon recovery
    Then the graph catches up to match LanceDB exactly
```

#### `graph_mcp_tools.feature`

```gherkin
Feature: The 10 new graph MCP tools

  Background: in-memory FastMCP client; FakeBackend-backed guru-graph

  Scenario Outline: Each tool round-trips through the MCP protocol
    When the MCP client calls <tool> with <args>
    Then the response shape matches <expected>
    And the guru-server REST endpoint <endpoint> was invoked exactly once

    Examples:
      | tool                        | args                                 | endpoint                          |
      | graph_describe              | node_id=<id>                         | GET /graph/describe/<id>          |
      | graph_neighbors             | node_id=<id>,direction=out,depth=2   | GET /graph/neighbors/<id>         |
      | graph_find                  | qualname_prefix=<p>                  | POST /graph/find                  |
      | graph_annotate              | node_id=<id>,kind=gotcha,body=<b>    | POST /graph/annotations           |
      | graph_delete_annotation     | annotation_id=<aid>                  | DELETE /graph/annotations/<aid>   |
      | graph_link                  | from_id,to_id,kind=calls             | POST /graph/links                 |
      | graph_unlink                | from_id,to_id,kind=calls             | DELETE /graph/links               |
      | graph_orphans               | limit=50                             | GET /graph/orphans                |
      | graph_reattach_orphan       | annotation_id,new_node_id            | POST /graph/orphans/<aid>/reattach |
      | graph_query                 | cypher="MATCH (n) RETURN count(n)"   | POST /graph/query (read_only=true)|

  Scenario: graph_query cannot smuggle writes
    When MCP calls graph_query(cypher="CREATE (x:Evil) RETURN x")
    Then the server rejects with {"error":"invalid_request"} OR Neo4j refuses the write transaction
    And no :Evil node exists
```

#### `skill_distribution.feature`

```gherkin
Feature: Guru skill is installed and updated safely

  Scenario: `guru init` installs the skill tree
    Given a fresh tmpdir project
    When I run `guru init`
    Then .claude/skills/guru-knowledge-base/SKILL.md exists
    And .claude/skills/guru-knowledge-base/references/{model,discovery,curation,annotation-shape,linking-patterns,orphans}.md all exist
    And .agents/skills/guru-knowledge-base is a symlink to the .claude path
    And MANIFEST.json contains a sha256 for every shipped file

  Scenario: `guru update` is a no-op on an up-to-date tree
    Given the skill was just installed
    When I run `guru update`
    Then no files are modified
    And stdout says "already up to date"

  Scenario: `guru update` overwrites unmodified files when the shipped version changes
    Given the skill was installed from guru v0.1.0
    And a new guru version ships updated SKILL.md
    When I run `guru update`
    Then the user's SKILL.md matches the new shipped version
    And MANIFEST.json is refreshed

  Scenario: `guru update` refuses to clobber user edits
    Given the user edited SKILL.md
    And a new guru version ships updated SKILL.md
    When I run `guru update`
    Then SKILL.md is untouched
    And stdout reports "modified by you, left alone"
    And exit code is 0

  Scenario: `guru update --force` backs up and overwrites
    Given the user edited SKILL.md
    When I run `guru update --force`
    Then SKILL.md.bak.<timestamp> contains the previous user content
    And SKILL.md matches the shipped version

  Scenario: `guru update --dry-run` writes nothing
    Given multiple files need updating
    When I run `guru update --dry-run`
    Then the listed changes match a subsequent real run
    But no files on disk changed
```

#### `parser_extensibility.feature`

```gherkin
Feature: Adding a new language parser is a pure extension

  Scenario: A test ProtobufParser is registered at startup
    Given the test registers ProtobufParser into the shared ParserRegistry via the init hook
    And a fixture has api/user.proto
    When `guru index` runs
    Then ProtobufParser.parse was called for api/user.proto exactly once
    And the chunks emitted appear in LanceDB with parser_name="protobuf"

  @real_neo4j
  Scenario: The new parser's graph output integrates with the schema
    Given ProtobufParser emits (:Document) + (:ProtoMessage) + (:ProtoField) + CONTAINS edges
    When the reconciliation runs
    Then those nodes exist and are reachable from (:Kb)-[:CONTAINS]->(:Document)
    And no existing scenarios from artifact_indexing.feature broke
```

#### `constitution_invariants.feature`

```gherkin
Feature: Non-negotiable architectural invariants

  Scenario: Indexing never blocks on graph I/O
    Given graph is enabled but daemon is hung (sleeps 30s on every request)
    When `guru index` runs with a 5s per-file budget
    Then `guru index` completes within the per-file budget × files count + small epsilon
    And LanceDB is fully populated
    And graph submissions were abandoned via graph_or_skip

  Scenario: MCP writes limited to annotations + links
    When MCP tool list is enumerated
    Then the only write-capable tools are graph_annotate, graph_delete_annotation,
                                            graph_link, graph_unlink, graph_reattach_orphan
    And no tool exists for upsert_kb, delete_kb, link_kbs, unlink_kbs, arbitrary Cypher writes

  Scenario: Graph-agnostic CLI + MCP unchanged
    When I diff the pre-feature and post-feature surfaces of
         search, get_document, list_documents, get_section, index_status,
         federated_search, list_peers, guru init, guru index, guru status
    Then their contracts are byte-identical
```

### Shared test infrastructure additions

```
tests/e2e/fixtures/polyglot/
├── src/pkg/__init__.py
├── src/pkg/auth.py
├── src/pkg/services/user.py
├── docs/guide.md
├── api/openapi.yaml
└── guru.json

tests/e2e/fixtures/protobuf_parser/
└── (test-only parser implementation + proto file)
```

New step files under `tests/e2e/features/steps/`: `artifact_steps.py`, `annotation_steps.py`, `orphan_steps.py`, `skill_steps.py`.

### CI wiring additions

- `make test-graph` extends to run the new `@real_neo4j` scenarios.
- `make test-all` runs combined `@real_ollama` + `@real_neo4j` scenarios for hybrid search.
- New CI job `artifact-graph-e2e` gated behind the `require-e2e-tests` label; uses Neo4j 5 service container + ready Ollama.

---

## Rollout — one umbrella plan, nine ordered PRs

```
Phase 1  — Foundation
  PR-1:  Parser contract + LanceDB metadata columns
  PR-2:  m0002 schema + ingest routes + first-class Document nodes (markdown only)

Phase 2  — Agent surface ships before language parsers
  PR-3:  Annotations subsystem (service + routes + GraphClient)
  PR-4:  Artifact links (RELATES edges + routes + GraphClient)
  PR-5:  Graph MCP tools (all 10) + guru-server /graph/* proxy routes
  PR-6:  Skill package + `guru init` seeds skill tree + `guru update` command

Phase 3  — Language parsers
  PR-7:  Python parser (tree-sitter)
  PR-8:  OpenAPI parser

Phase 4  — Housekeeping
  PR-9:  ARCHITECTURE.md amendments + cross-references + open-question closeouts
```

### Per-PR checkpoint

**PR-1 — Parser contract + LanceDB columns**
- Scope. `GraphNode` / `GraphEdge` / `ParseResult` dataclasses; `ParserRegistry`. Extended `Chunk`. LanceDB additive columns. Retrofit `MarkdownParser` to return `ParseResult` (graph output captured but not yet submitted). No user-visible behaviour change.
- Deps. None.
- Success. `make test` green; existing markdown scenarios pass; new unit tests green.
- Risk. LanceDB additive schema evolution. Ships a one-shot table rebuild if schema-evolve is rejected.

**PR-2 — m0002 schema + ingest routes + Document nodes land in Neo4j**
- Scope. Migration. `/ingest/parse-result` + `/ingest/documents/{id}` routes on `guru-graph`. `GraphClient.submit_parse_result`. Indexer wires them via `graph_or_skip`. Markdown files now produce `(:Document)` + `(:MarkdownSection)` end-to-end.
- Deps. PR-1.
- Success. `make test-graph` green including new `@real_neo4j` migration + reconciliation tests. `graph_optional.feature::Full guru lifecycle with graph disabled` + markdown-only subset of `artifact_indexing.feature` pass.
- Risk. Existing users' v1 stores. Idempotent migration; refuses downgrade.

**PR-3 — Annotations subsystem**
- Scope. `(:Annotation)` node + `[:ANNOTATES]` edge + replace vs append semantics. Routes: `POST /annotations`, `DELETE /annotations/{id}`, `GET /annotations/orphans`, `POST /annotations/{id}/reattach`. Service layer with authorship stamping. `GraphClient` methods. Orphan-preserving deletion wired into reconciliation.
- Deps. PR-2.
- Success. `annotations_and_curation.feature` + `orphan_triage.feature` skeleton scenarios pass.
- Risk. Author stamping via trustworthy HTTP header from guru-server. Spoof test in unit layer.

**PR-4 — Artifact links**
- Scope. `RELATES {kind}` edges; `ArtifactLinkKind` enum; `POST /relates`, `DELETE /relates`; `GraphClient` methods; 422 on unknown kinds.
- Deps. PR-2.
- Success. Kb-level / markdown-level scenarios from `artifact_links.feature` pass; Python/OpenAPI-level scenarios remain skipped until PR-7/PR-8.
- Risk. Low; additive.

**PR-5 — Graph MCP tools + `guru-server` `/graph/*` proxy**
- Scope. Ten `/graph/*` routes on guru-server (proxy + `graph_or_skip` + author stamping + read-only enforcement). Ten MCP tools. CLI reads: `describe`, `neighbors`, `find`, `annotations`, `orphans`.
- Deps. PR-3, PR-4.
- Success. `graph_mcp_tools.feature` passes with FakeBackend. `graph_optional.feature` graph-disabled scenarios pass.
- Risk. 20+ new endpoints. OpenAPI schema-shape test locks surface.

**PR-6 — Skill package + `guru init` + `guru update`**
- Scope. Skill asset tree at `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/`. Hatchling wheel include. `guru init` seeding. `guru update` with drift detection, `--force`, `--dry-run`. Windows symlink fallback.
- Deps. PR-5.
- Success. `skill_distribution.feature` six scenarios pass. Frontmatter lints. Smoke test: fresh project → `guru init` → scripted agent session invokes `graph_annotate`.
- Risk. Cross-platform filesystem. Windows fallback documented.

**PR-7 — Python parser**
- Scope. `PythonParser` (tree-sitter-python, pinned). Modules, classes, functions, methods, imports, inheritance.
- Deps. PR-2.
- Success. `artifact_indexing.feature` `@real_neo4j @real_ollama` scenarios pass. `test_python_parser.py` 15+ assertions.
- Risk. Tree-sitter wheel availability on macOS ARM + Linux x86_64 for Python 3.13. Binding + grammar commits both pinned.

**PR-8 — OpenAPI parser**
- Scope. `OpenApiParser` (JSON + YAML, 3.0 + 3.1). `(:OpenApiSpec)`, `(:OpenApiOperation)`, `(:OpenApiSchema)`. Local + cross-file `$ref` resolution. Circular-safe. `oneOf`/`anyOf`/`allOf` collapsed. Malformed → fail-soft.
- Deps. PR-2.
- Success. OpenAPI scenarios in `artifact_indexing.feature` pass. `test_openapi_parser.py` covers 3.0 + 3.1 fixtures. `artifact_links.feature::Agent manually links a class to its OpenAPI contract` passes.
- Risk. Messy real-world OpenAPI. Spec-compliant only; invalid → `Document.properties.valid=false`.

**PR-9 — ARCHITECTURE.md amendments + docs closeout**
- Scope. Four amendments (from this spec) land. Cross-link this spec, graph-plugin spec, read-only CLI spec. `AGENTS.md` gains a single line pointing at the skill.
- Deps. PR-1..8.
- Success. Docs render cleanly; links resolve.
- Risk. Nil.

### Cross-cutting

- **Feature flags / kill switches.** None. Graph-disabled mode is the global kill switch.
- **Version bumps.** Protocol `1.0.0 → 1.1.0` (MINOR) in PR-2. Package versions follow `uv-dynamic-versioning` from git tags.
- **Deprecations.** None. All additive.
- **Data migration for existing users.** m0002 forward-only + idempotent. Existing v1 graph stores auto-upgrade on first daemon start. Pre-PR-2 LanceDB indexes materialise `(:Document)` nodes on the next `guru index`.
- **Rollback.** Any PR rolls back to predecessor state, except post-PR-2 m0002 — downgrade requires wiping `~/Library/Application Support/guru/graph/` (documented in release notes).

### Success criteria for the umbrella feature

1. All 10 BDD feature files from this spec pass on CI.
2. Greenfield project: `guru init` → Claude Code session with installed skill → the agent, unprompted beyond a natural investigation request, calls `search()`, pivots via `graph_describe`, writes at least one gotcha with correct author stamping, and surfaces orphans after a rename. End-to-end demo recording counts as acceptance.
3. Graph-disabled: same project lifecycle produces byte-identical output to pre-feature behaviour except for the presence of artifact chunks in search results.
4. Adding a hypothetical `RustParser` requires touching exactly two places: the parser file itself and one `register()` call. `parser_extensibility.feature` enforces this.

---

## Open questions / deferred work

- **Python call-site detection** (`CALLS` edges). Tree-sitter can extract call expressions, but name resolution across modules is noisy without a type-checker. Deferred to a follow-up spec.
- **Cross-project artifact discovery.** Machine-global artifact search (e.g. "find `User` classes across all my projects") is deliberately out of scope. The federation surface covers the KB-level case; artifact-level awaits demand.
- **Neo4j vector index.** Once `graph_query` is used heavily, in-graph semantic neighbourhood traversal becomes valuable. Can be added as a migration that reads LanceDB vectors into Neo4j's vector index.
- **Orphan TTL.** Auto-expiry deferred. A `guru graph orphans --older-than 30d` CLI command can be added when orphan accumulation becomes a real problem.
- **Agent-invented link kinds.** Closed vocabulary in v1; MINOR schema bumps add new kinds. An "allow-list with review" pattern is conceivable later.
- **TS/JS/JSON-Schema parsers.** Explicit follow-up specs. The parser contract is designed to make them pure extensions.
