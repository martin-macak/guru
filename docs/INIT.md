# ADR-001: Local RAG Knowledge Base with MCP Interface for Spec-Driven Development

| Field        | Value            |
| ------------ | ---------------- |
| **Status**   | Proposed         |
| **Date**     | 2026-04-09       |
| **Author**   | Martin           |
| **Deciders** | Engineering team |

---

## Context and Problem Statement

Our monorepo follows spec-driven development and contains a large corpus of markdown specification files. AI coding agents (Claude Code, Cursor, Continue.dev) lack awareness of these specs during development — they cannot search, retrieve, or reason over project-specific domain knowledge.

We need a **local-first, privacy-respecting** tool that:

1. Indexes markdown spec files into a searchable knowledge base.
2. Exposes that knowledge to AI agents via MCP (Model Context Protocol).
3. Runs entirely on a developer's MacBook (M2/M3/M4) with no cloud dependencies.
4. Handles incremental updates as specs evolve.
5. Preserves markdown structure (headers, frontmatter, cross-references, code blocks).

## Decision Drivers

- **Privacy**: Specs contain proprietary domain knowledge. No data leaves the machine.
- **Developer experience**: Zero Docker, zero external servers, minimal setup.
- **Spec structure preservation**: Header hierarchy, YAML frontmatter, and cross-references are first-class metadata — not discarded during chunking.
- **Agent-agnostic**: MCP is the standard interface; the tool must work with any MCP-compatible client.
- **Single language**: Python-only codebase to reduce toolchain complexity.
- **Apple Silicon performance**: Must run efficiently on M-series Macs without GPU dependencies.

---

## Decision: Technical Stack

### Vector Database → LanceDB

**Chosen**: `lancedb` (v0.27+)

**Rationale**:

- Truly serverless — no background process, no Docker. Just a library import.
- Memory-mapped file access handles datasets larger than RAM.
- Lance columnar format claims 100x faster scans than Parquet.
- Sub-100ms search on MacBook hardware at million-vector scale.
- Native Python SDK with SQL-like metadata filtering.
- IVF-PQ indexing with ~95% accuracy at millisecond latency.
- Automatic disk persistence — no manual save/load.

**Rejected alternatives**:
| Alternative | Reason for rejection |
|---|---|
| ChromaDB | Good option, but more memory-dependent. LanceDB's disk-efficient design better suits large spec corpora. |
| Qdrant (local mode) | Python-only local mode limited to ~20K points with brute-force search. Insufficient without Docker server. |
| sqlite-vec | DiskANN indexing still alpha. Brute-force degrades past ~100K vectors. |
| FAISS | No metadata storage, no persistence, no filtering. A search library, not a database. |

### Embedding Model → nomic-embed-text v1.5 via Ollama

**Chosen**: `nomic-embed-text` served by Ollama

**Rationale**:

- 137M parameters, 274MB on disk — lightweight on M2.
- **8192-token context window** — critical for spec sections that routinely exceed 512 tokens.
- 768-dimension vectors, 62.39 MTEB score — best quality/size ratio in class.
- Matryoshka dimension reduction: truncate to 256 dims with ~1.5% quality loss if storage is a concern.
- 15–50ms per embedding call on Apple Silicon via Ollama's localhost API.
- Handles mixed code/prose well — important for specs containing API examples.
- Setup: `ollama pull nomic-embed-text` (one command).

**Rejected alternatives**:
| Alternative | Reason for rejection |
|---|---|
| mxbai-embed-large | Higher MTEB (64.68) but 512-token context limit. Unacceptable for spec files. |
| Qwen3-Embedding 8B | Best quality (70.58 MTEB) but ~5GB RAM with Q4 quantization. Overkill for this use case. |
| FastEmbed (ONNX) | No Ollama dependency is nice, but model selection is narrower and runtime management is manual. |
| static-retrieval-mrl-en-v1 | 100-400x faster but ~13% quality loss. Useful for bulk re-indexing only, not primary retrieval. |

### Ingestion & Chunking → LlamaIndex MarkdownNodeParser

**Chosen**: `llama-index-core` with `MarkdownNodeParser` + `python-frontmatter`

**Rationale**:

- `MarkdownNodeParser` splits on header levels, attaches header breadcrumb as metadata, maintains prev/next node relationships.
- `HierarchicalNodeParser` creates multi-granularity nodes (document → section → paragraph) with parent-child relationships.
- `AutoMergingRetriever` reassembles parent nodes when enough child nodes match — ideal for spec retrieval where agents need full section context.
- `python-frontmatter` extracts YAML metadata (title, version, status, owner, tags) at parse time.
- LlamaIndex has first-class LanceDB integration via `llama-index-vector-stores-lancedb`.

**Chunking strategy**:

```
Level 1 (Document)  → Full spec with summary + all frontmatter
Level 2 (Section)   → H2-level sections, 500–1000 tokens
Level 3 (Subsection)→ H3-level chunks, 200–500 tokens
```

Each chunk carries:

- `file_path` — source file in monorepo
- `header_breadcrumb` — e.g. `"Auth > OAuth > Token Refresh"`
- Frontmatter fields — `title`, `version`, `status`, `owner`, `tags`
- `cross_references` — parsed from markdown links to other spec files
- `parent_chunk_id` / `chunk_level` — for parent-child retrieval
- `content_type` — flags for code blocks, tables, diagrams

**Rejected alternatives**:
| Alternative | Reason for rejection |
|---|---|
| LangChain MarkdownHeaderTextSplitter | Good standalone splitter, but LlamaIndex's hierarchical indexing + AutoMergingRetriever is more powerful for our use case. |
| Chonkie | Lightweight and fast, but less mature ecosystem. Can be added later as a LlamaIndex plugin if needed. |
| Unstructured.io | Overkill — designed for mixed-format pipelines (PDF, HTML, etc.). We only have markdown. |

### MCP Server → FastMCP (Python SDK)

**Chosen**: `mcp` package with `FastMCP` class, stdio transport

**Rationale**:

- Official Anthropic Python SDK for MCP (`pip install mcp`).
- Decorator-based tool definition — minimal boilerplate.
- stdio transport is simplest for local agent integration (agent spawns server as subprocess).
- Supports SSE and streamable-HTTP transports for future multi-client scenarios.

**Exposed MCP tools**:

| Tool                                      | Description                                          |
| ----------------------------------------- | ---------------------------------------------------- |
| `search_specs(query, n_results, filters)` | Semantic + metadata-filtered search over spec corpus |
| `get_spec(file_path)`                     | Retrieve full spec content by path                   |
| `list_specs(status, owner, tag)`          | Browse spec catalog with optional filters            |
| `get_spec_section(file_path, header)`     | Retrieve specific section of a spec                  |
| `find_related_specs(file_path)`           | Find specs cross-referenced by a given spec          |

**Rejected alternatives**:
| Alternative | Reason for rejection |
|---|---|
| `mcp-local-rag` (npx) | TypeScript/Node.js — violates single-language constraint. |
| chroma-mcp / qdrant-mcp | Tied to specific vector DBs we're not using. |
| LlamaIndex `workflow_as_mcp()` | Adds LlamaIndex runtime dependency to the MCP server. Prefer thin MCP layer over direct LanceDB queries for lower latency. |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  AI Agent (Claude Code / Cursor / Continue.dev)     │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  MCP Client                                   │  │
│  └──────────────────┬────────────────────────────┘  │
└─────────────────────┼───────────────────────────────┘
                      │ stdio
┌─────────────────────┼───────────────────────────────┐
│  MCP Server (FastMCP)                               │
│  ┌──────────────────┴────────────────────────────┐  │
│  │  Tools: search_specs, get_spec, list_specs,   │  │
│  │         get_spec_section, find_related_specs   │  │
│  └──────────────────┬────────────────────────────┘  │
│                     │                                │
│  ┌──────────────────┴────────────────────────────┐  │
│  │  Query Engine                                 │  │
│  │  - Hybrid search (semantic + keyword)         │  │
│  │  - Metadata filtering                         │  │
│  │  - Parent-child chunk resolution              │  │
│  └──────────────────┬────────────────────────────┘  │
│                     │                                │
│  ┌──────────────────┴──────┐  ┌──────────────────┐  │
│  │  LanceDB               │  │  Ollama           │  │
│  │  (embedded, on-disk)   │  │  nomic-embed-text │  │
│  └─────────────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
                      ▲
                      │ file watch (ingestion)
┌─────────────────────┼───────────────────────────────┐
│  Monorepo                                           │
│  specs/                                             │
│  ├── auth/                                          │
│  │   ├── oauth-flow.md                              │
│  │   └── token-refresh.md                           │
│  ├── api/                                           │
│  │   ├── rest-conventions.md                        │
│  │   └── error-codes.md                             │
│  └── data/                                          │
│      ├── schema-v2.md                               │
│      └── migration-strategy.md                      │
└─────────────────────────────────────────────────────┘
```

---

## Python Dependencies

```toml
[project]
name = "spec-rag-mcp"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0",
    "lancedb>=0.27",
    "llama-index-core>=0.14",
    "llama-index-vector-stores-lancedb",
    "llama-index-embeddings-ollama",
    "python-frontmatter>=1.1",
    "watchdog>=4.0",         # file system watcher for incremental indexing
]
```

**External dependency**: Ollama (installed separately via `brew install ollama` or from ollama.com).

---

## Key Risks and Mitigations

| Risk                                                      | Impact                          | Mitigation                                                                                               |
| --------------------------------------------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Ollama not installed / model not pulled                   | Embeddings fail silently        | CLI check at startup: verify `ollama list` contains `nomic-embed-text`. Fail fast with actionable error. |
| Spec corpus exceeds single-machine capacity               | Unlikely but possible           | LanceDB handles datasets larger than RAM via memory mapping. Monitor index size.                         |
| Chunk boundaries split critical context                   | Poor retrieval quality          | Parent-child indexing with AutoMergingRetriever. Never split code blocks mid-block.                      |
| Cross-references between specs not resolved               | Agent misses related context    | Parse markdown links at ingestion, store bidirectional edges in metadata.                                |
| MCP transport compatibility across agents                 | Agent can't connect             | Start with stdio (universally supported). Add SSE transport as opt-in.                                   |
| Embedding model quality insufficient for code-heavy specs | Low recall on technical queries | Benchmark against FastEmbed's `jina-embeddings-v2-base-code` as fallback.                                |

---

## Implementation Plan

### Phase 1: Core Pipeline (MVP)

- [ ] Project scaffolding (`pyproject.toml`, CLI entry point)
- [ ] Markdown ingestion: walk spec directory, extract frontmatter, parse headers
- [ ] Chunking: LlamaIndex `MarkdownNodeParser` with hierarchical splitting
- [ ] Embedding: Ollama `nomic-embed-text` integration
- [ ] Storage: LanceDB table with vector + metadata columns
- [ ] MCP server: `search_specs` and `get_spec` tools via FastMCP
- [ ] Claude Code integration test

### Phase 2: Retrieval Quality

- [ ] Hybrid search (semantic + BM25/keyword)
- [ ] Parent-child chunk resolution (return full section when subsections match)
- [ ] Cross-reference resolution and `find_related_specs` tool
- [ ] Metadata filtering on frontmatter fields
- [ ] Retrieval quality benchmarks against known spec queries

### Phase 3: Developer Experience

- [ ] `watchdog`-based file watcher for incremental re-indexing on spec changes
- [ ] CLI commands: `index`, `search`, `serve`, `status`
- [ ] Configuration file (`.spec-rag.yaml`) for spec directory paths, exclusions, chunk sizes
- [ ] Cache invalidation: re-embed only changed files (hash-based diff)

### Phase 4: Hardening

- [ ] SSE transport for multi-client scenarios
- [ ] Embedding model benchmarking harness (swap models, compare retrieval)
- [ ] Index compaction and garbage collection for deleted specs
- [ ] Logging and observability (query latency, cache hit rate, index size)

---

## Consequences

**Positive**:

- AI agents gain full awareness of project specs during development.
- Zero cloud dependency — all data stays on the developer's machine.
- Single Python codebase — no polyglot toolchain overhead.
- MCP interface is agent-agnostic — works with any MCP client today and in the future.
- Hierarchical chunking preserves spec structure that naive RAG destroys.

**Negative**:

- Requires Ollama as an external runtime (not pure `pip install`).
- LlamaIndex is a heavy dependency (~50+ transitive packages). May want to replace with direct LanceDB queries in Phase 4 if the abstraction isn't paying for itself.
- No shared team index — each developer maintains their own local index. Acceptable for now; revisit if team-wide consistency becomes an issue.

**Neutral**:

- Chunking strategy will need tuning per-project. The defaults (500–800 tokens, H2/H3 split) are a starting point, not a final answer.
- Embedding model choice can be swapped without architectural changes. nomic-embed-text is the best default today; this will change.
