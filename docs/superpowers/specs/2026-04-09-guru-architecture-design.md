# Guru Architecture Design Spec

| Field        | Value            |
| ------------ | ---------------- |
| **Status**   | Approved         |
| **Date**     | 2026-04-09       |
| **Author**   | Martin           |

---

## Overview

Guru is a local-first, privacy-respecting knowledge-base manager that indexes documents in a git repo and serves them to AI agents via RAG over MCP. It runs entirely on a developer's MacBook (Apple Silicon) with no cloud dependencies.

## Architecture: Server-Centric

The **guru-server** is the single process that owns all state: LanceDB storage, Ollama embedding calls, document indexing. All other components are stateless clients.

```
AI Agent (Claude Code / Cursor / Continue.dev)
    │ stdio
guru-mcp (MCP protocol adapter)
    │ HTTP-over-UDS
guru-server (FastAPI daemon)
    ├── LanceDB (embedded, on-disk)
    └── Ollama (nomic-embed-text)

Developer terminal
    │
guru-cli (click commands / Textual TUI)
    │ HTTP-over-UDS
guru-server
```

---

## Workspace Layout

```
guru/                              # root uv workspace
├── pyproject.toml                 # workspace config
├── guru.json                      # optional project-level indexing rules
├── packages/
│   ├── guru-core/                 # shared client SDK + types
│   │   └── src/guru_core/
│   │       ├── client.py          # HTTP-over-UDS client (httpx)
│   │       ├── discovery.py       # walk up to find .guru/, read PID/socket
│   │       ├── autostart.py       # spawn server if not running
│   │       └── types.py           # shared request/response models
│   │
│   ├── guru-server/               # daemon — owns all state
│   │   └── src/guru_server/
│   │       ├── app.py             # FastAPI app
│   │       ├── api/               # REST endpoint handlers
│   │       ├── ingestion/         # pluggable document parsers
│   │       │   ├── base.py        # ingestion protocol/interface
│   │       │   └── markdown.py    # LlamaIndex markdown parser
│   │       ├── search/            # LanceDB query engine
│   │       ├── embedding/         # Ollama client
│   │       └── startup.py         # preflight checks (ollama, model)
│   │
│   ├── guru-mcp/                  # MCP protocol adapter (thin client)
│   │   └── src/guru_mcp/
│   │       └── server.py          # FastMCP, translates tools -> REST
│   │
│   └── guru-cli/                  # CLI + TUI (thin client)
│       └── src/guru_cli/
│           ├── cli.py             # click commands
│           └── tui/               # Textual app
```

### Dependency Graph

```
guru-cli    -> guru-core
guru-mcp    -> guru-core
guru-server -> (standalone, no internal workspace deps)
guru-core   -> httpx (+ shared types only)
```

---

## Server (guru-server)

### Tech Stack

- **Framework**: FastAPI + uvicorn (async, native UDS support)
- **Vector DB**: LanceDB (serverless, memory-mapped, embedded)
- **Embeddings**: nomic-embed-text via Ollama (8192-token context, 768-dim vectors)
- **Ingestion**: LlamaIndex MarkdownNodeParser + HierarchicalNodeParser
- **Transport**: HTTP over Unix domain socket

### Startup Sequence

1. Check `ollama` binary on PATH -> fail with: `brew install ollama`
2. Start `ollama serve` as a managed subprocess
3. Check `nomic-embed-text` model available (`ollama list`) -> fail with: `ollama pull nomic-embed-text`
4. Load and resolve configuration (see Configuration section)
5. Initialize LanceDB at `.guru/db/`
6. Bind Unix domain socket at `.guru/guru.sock`
7. Write `.guru/guru.pid`
8. Start FastAPI via uvicorn with `--uds .guru/guru.sock`

All preflight checks fail fast with actionable error messages and instructions.

### Shutdown

- Remove `guru.sock`
- Remove `guru.pid`
- Terminate managed `ollama serve` process

### REST API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/search` | Semantic + metadata-filtered search |
| `GET` | `/documents` | List documents with optional filters |
| `GET` | `/documents/{path}` | Get full document with metadata |
| `GET` | `/documents/{path}/sections/{header_path}` | Get specific section by header breadcrumb |
| `POST` | `/index` | Trigger indexing (applies resolved config rules to project root, optional path override) |
| `GET` | `/status` | Server health, index stats, staleness info |

### Data Directory

```
.guru/                     # gitignored, project-local
├── guru.sock              # Unix domain socket
├── guru.pid               # server PID
└── db/                    # LanceDB data files
```

### Ingestion Protocol

An abstract base class defines how a file format is parsed into chunks with metadata. This enables future format support without modifying the core pipeline.

**Interface contract:**
- Input: file path + rule config (labels, chunking overrides)
- Output: list of chunks, each with content, metadata (frontmatter, labels, header breadcrumb, file path), and parent-child relationships

**Implementations:**
- **Markdown** (MVP): LlamaIndex MarkdownNodeParser + HierarchicalNodeParser + python-frontmatter
- Future: RST, plain text, YAML/JSON schemas — each implements the same interface

**Chunking strategy (markdown):**
```
Level 1 (Document)   -> Full doc with summary + all frontmatter
Level 2 (Section)    -> H2-level sections, 500-1000 tokens
Level 3 (Subsection) -> H3-level chunks, 200-500 tokens
```

Each chunk carries:
- `file_path` — source file
- `header_breadcrumb` — e.g. "Auth > OAuth > Token Refresh"
- Frontmatter fields — title, version, status, owner, tags (whatever exists)
- Labels — from matching config rules
- `parent_chunk_id` / `chunk_level` — for parent-child retrieval
- `content_type` — flags for code blocks, tables, diagrams

---

## Client Discovery & Auto-Start (guru-core)

### Discovery Algorithm

1. Start from current working directory
2. Walk up parent directories looking for `.guru/` (same pattern as git looking for `.git/`)
3. If found: check `guru.sock` exists and `guru.pid` is alive
4. If socket exists but PID is dead -> stale state -> clean up socket/pid files -> auto-start
5. If no `.guru/` found -> error: "Not a guru project. Run `guru init` first."

### Auto-Start

1. Spawn `guru-server` as a detached background process
2. Wait for `guru.sock` to appear (poll with short timeout, ~5s max)
3. Health check via `GET /status` over the socket
4. If startup fails -> surface the server's preflight error (e.g., "ollama not found")

### HTTP Client

`httpx.AsyncClient` with Unix domain socket transport. All calls go through a single `GuruClient` class that handles:
- Discovery (find `.guru/`)
- Auto-start (spawn server if needed)
- Request/response serialization
- Error handling with actionable messages

---

## MCP Server (guru-mcp)

### Transport

stdio — the agent spawns the MCP process as a subprocess. Universal across Claude Code, Cursor, Continue.dev.

### Runtime Flow

1. Agent spawns `guru-mcp` via stdio
2. `guru-mcp` uses `guru-core` to discover `.guru/` and auto-start the server
3. Tool calls are translated 1:1 into REST calls via `GuruClient`
4. Results returned to agent as MCP tool responses

### MCP Tools

**MVP:**

| Tool | Maps to | Description |
|------|---------|-------------|
| `search(query, n_results?, filters?)` | `POST /search` | Semantic search over knowledge base |
| `get_document(file_path)` | `GET /documents/{path}` | Full document with metadata |
| `list_documents(filters?)` | `GET /documents` | Browse document catalog |
| `get_section(file_path, header_path)` | `GET /documents/{path}/sections/{header_path}` | Specific section by header breadcrumb |
| `index_status()` | `GET /status` | Index health, staleness, errors |

**Phase 2:**

| Tool | Description |
|------|-------------|
| `find_related(file_path)` | Cross-reference graph traversal |

### Agent Configuration (.mcp.json)

```json
{
  "mcpServers": {
    "guru": {
      "command": "uv",
      "args": ["run", "guru-mcp"]
    }
  }
}
```

The MCP process inherits the working directory from the agent, so discovery naturally finds the correct `.guru/`.

---

## CLI (guru-cli)

### Entry Point

`guru` command via click. Running `guru` with no arguments launches the TUI.

### Commands

```
guru                               # launch Textual TUI (default)
guru init                          # create .guru/ in current directory
guru server start                  # explicitly start server
guru server stop                   # stop server
guru server status                 # health, index stats

guru index [PATH]                  # index a directory (default: current dir)
guru search "query" [--filters]    # semantic search
guru doc <file_path>               # get document with metadata
guru doc <file_path> --section "Auth > OAuth"  # get specific section
guru list [--filters]              # browse document catalog

guru config                        # show resolved config with provenance
guru tui                           # explicit TUI launch (same as bare guru)
```

Every command except `guru init` triggers auto-start if the server isn't running.

### TUI Mode (Textual)

Interactive dashboard:
- Search input field
- Results list with relevance scores
- Document viewer panel (preview selected result)
- Status bar (server status, index stats)

---

## Configuration System

### Rule Schema

```json
{
  "ruleName": "string (unique identifier, required)",
  "match": {
    "glob": "string (file glob pattern, required)"
  },
  "exclude": false,
  "labels": ["optional", "string", "array"],
  "chunking": {
    "max_tokens": 800,
    "split_level": "h2"
  }
}
```

- `ruleName` + `match` are required. Everything else is optional.
- `exclude: true` prevents matched files from being indexed.
- `labels` attach filterable metadata to all documents matched by the rule.
- `chunking` overrides default chunking behavior for matched documents.

### Config File Locations

**Resolution chain (highest to lowest precedence):**

1. `./guru.json` — project root, version-controlled, shared with team
2. `./.guru/config.json` — project-local, gitignored (fallback if no guru.json)
3. `~/.config/guru/config.json` — user-global defaults

### Merge Semantics

- Load global config (`~/.config/guru/config.json`) as base rule set
- Load local config (`./guru.json` preferred, `./.guru/config.json` fallback)
- Rules with the same `ruleName` in local **fully replace** the global version (no deep merge of fields within a rule)
- Local rules with new names are **appended** to the global set
- If no config exists anywhere, apply hardcoded default:

```json
[
  {
    "ruleName": "default",
    "match": {
      "glob": "**/*.md"
    }
  }
]
```

### `guru config` Command

Prints the resolved merged configuration with provenance — shows which file each rule originated from, making it easy to debug rule conflicts.

---

## Phasing

### Phase 1: Core Pipeline (MVP)

- Project scaffolding (workspaces, dependencies)
- Server: FastAPI + uvicorn over UDS
- Server: preflight checks (ollama, model)
- Server: markdown ingestion via LlamaIndex
- Server: LanceDB storage + semantic search
- Server: REST API (search, get_document, list_documents, get_section, status, index)
- Core: UDS client, discovery, auto-start
- MCP: FastMCP with 5 tools over stdio
- CLI: click commands (init, server, index, search, doc, list, config)
- Configuration: rule-based JSON with merge chain

### Phase 2: Retrieval Quality

- Hybrid search (semantic + BM25/keyword)
- Parent-child chunk resolution (AutoMergingRetriever)
- Cross-reference resolution and `find_related` tool
- Retrieval quality benchmarks

### Phase 3: Developer Experience

- File watcher (watchdog) for incremental re-indexing
- CLI TUI (Textual dashboard)
- Cache invalidation: re-embed only changed files (hash-based diff)

### Phase 4: Hardening

- SSE/streamable-HTTP transport for MCP (multi-client)
- Embedding model benchmarking harness
- Index compaction and garbage collection
- Logging and observability
