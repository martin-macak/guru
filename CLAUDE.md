# Guru Project Instructions

## What is this project?

Guru is a local-first knowledge-base manager that indexes documents in a git repo and
serves them to AI agents via RAG over MCP. It runs entirely on a developer's MacBook
with no cloud dependencies.

## Architecture

Read ARCHITECTURE.md before making any changes. It is the architecture constitution —
everything in it is a fact. If code contradicts ARCHITECTURE.md, the code is wrong.

## Project Structure

This is a uv workspace monorepo with four packages under `packages/`:

- **guru-core**: Shared client SDK (discovery, auto-start, HTTP-over-UDS client, types)
- **guru-server**: FastAPI daemon that owns all state (LanceDB, Ollama, ingestion)
- **guru-mcp**: MCP protocol adapter (thin client, FastMCP, stdio)
- **guru-cli**: CLI (click) + TUI (Textual)

## Key Rules

- guru-server is the ONLY component that accesses LanceDB or Ollama
- guru-mcp and guru-cli are thin clients — they talk to the server via guru-core
- Transport is HTTP over Unix domain socket at `.guru/guru.sock`
- No TCP ports are used
- `.guru/` is runtime state, always gitignored
- `guru.json` is project config, version-controlled

## Dependencies Between Packages

```
guru-cli    -> guru-core
guru-mcp    -> guru-core
guru-server -> (no internal deps)
guru-core   -> httpx
```

Do not add cross-dependencies that violate this graph.

## Tech Stack

- FastAPI + uvicorn (server)
- LanceDB (vector storage)
- Ollama + nomic-embed-text (embeddings)
- LlamaIndex (markdown ingestion/chunking)
- FastMCP (MCP server)
- click (CLI commands)
- Textual (TUI)
- httpx (HTTP client over UDS)

## Commands

```bash
uv sync --all-packages          # install all workspace packages
uv run guru                     # run CLI (launches TUI with no args)
uv run guru-server              # run server directly
uv run guru-mcp                 # run MCP server (stdio)
```

## Design Docs

- `docs/INIT.md` — initial ADR with technology research and decisions
- `docs/superpowers/specs/2026-04-09-guru-architecture-design.md` — architecture design spec
