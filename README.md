# Guru

A local-first knowledge-base manager that indexes markdown documents in a git repo and serves them to AI agents via RAG over MCP. Runs entirely on your MacBook with no cloud dependencies.

## What it does

- Indexes markdown files with YAML frontmatter into a vector database (LanceDB)
- Embeds content using Ollama (nomic-embed-text) running locally
- Serves knowledge to AI agents via MCP (Model Context Protocol)
- Provides a CLI for indexing, searching, and retrieving documents
- Rule-based configuration for labeling and organizing documents

## Architecture

```
AI Agent (Claude Code / Cursor / Continue.dev)
    | stdio
guru-mcp (MCP protocol adapter)
    | HTTP-over-UDS
guru-server (FastAPI daemon)
    |-- LanceDB (embedded vector storage)
    |-- Ollama (nomic-embed-text embeddings)

Developer terminal
    |
guru-cli (click commands / Textual TUI)
    | HTTP-over-UDS
guru-server
```

All state is owned by `guru-server`. Clients (`guru-mcp`, `guru-cli`) connect via HTTP over Unix domain sockets through the shared `guru-core` SDK.

## Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (package manager)
- [Ollama](https://ollama.com) with `nomic-embed-text` model

```bash
brew install ollama
ollama pull nomic-embed-text
```

## Quick start

```bash
# Install
uv sync --all-packages

# Initialize a project
cd /path/to/your/repo
uv run guru init

# Index your markdown files
uv run guru index

# Search
uv run guru search "authentication flow"

# List indexed documents
uv run guru list
```

## Configuration

Create `guru.json` in your project root (or let `guru init` create defaults):

```json
[
  {
    "ruleName": "docs",
    "match": { "glob": "docs/**/*.md" },
    "labels": ["documentation"]
  },
  {
    "ruleName": "specs",
    "match": { "glob": "specs/**/*.md" },
    "labels": ["spec"]
  },
  {
    "ruleName": "exclude-vendor",
    "match": { "glob": "vendor/**" },
    "exclude": true
  }
]
```

Config resolution: `./guru.json` > `./.guru/config.json` > `~/.config/guru/config.json`. Rules merge by `ruleName` (local replaces global, new names appended).

## MCP integration

Add to your `.mcp.json`:

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

Available MCP tools: `search`, `get_document`, `list_documents`, `get_section`, `index_status`.

## CLI commands

```
guru                     # launch TUI (Phase 3)
guru init                # initialize .guru/ in current directory
guru index [PATH]        # index documents
guru search "query"      # semantic search
guru doc <path>          # get full document
guru doc <path> -s "H"   # get specific section
guru list                # list all indexed documents
guru config              # show resolved config
guru server start|stop|status
```

## Development

```bash
uv sync --all-packages              # install everything
uv run pytest                       # unit + integration tests
uv run behave tests/e2e/features/   # BDD e2e tests
./scripts/run-behave-parallel.sh    # e2e tests in parallel
```

## Project structure

```
packages/
  guru-core/     shared client SDK (types, discovery, auto-start, HTTP client)
  guru-server/   FastAPI daemon (LanceDB, Ollama, ingestion, REST API)
  guru-mcp/      MCP protocol adapter (FastMCP, stdio)
  guru-cli/      CLI (click) + TUI (Textual)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture constitution.
