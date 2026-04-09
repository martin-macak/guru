# Architecture Constitution

This document contains non-breakable rules and decisions that govern the guru project.
Everything in this document is a fact. Anything in contradiction must be assessed as a
potential bug or error and questioned.

---

## Core Principle

Guru is a **local-first, privacy-respecting** knowledge-base manager. No data leaves
the developer's machine. There are zero cloud dependencies.

## Architecture: Server-Centric

- **guru-server** is the single process that owns all state: LanceDB, Ollama, indexing.
- **guru-mcp** and **guru-cli** are stateless thin clients that call the server's REST API.
- No component other than guru-server may access LanceDB or Ollama directly.

## Transport: Unix Domain Sockets

- Server listens on `.guru/guru.sock` (HTTP over UDS).
- No TCP ports. No firewall prompts. No port collisions between projects.
- MCP and CLI connect to the server exclusively via UDS through guru-core.

## Workspace Structure

```
packages/
  guru-core/    -> shared client SDK (discovery, auto-start, HTTP client, types)
  guru-server/  -> daemon (FastAPI + uvicorn, LanceDB, Ollama, ingestion)
  guru-mcp/     -> MCP protocol adapter (FastMCP, stdio transport)
  guru-cli/     -> CLI (click) + TUI (Textual)
```

## Dependency Rules

- `guru-cli` depends on `guru-core`. No other internal dependency.
- `guru-mcp` depends on `guru-core`. No other internal dependency.
- `guru-server` has zero internal workspace dependencies.
- `guru-core` is a lightweight SDK: `httpx` + shared types. No heavy dependencies.

## Server Lifecycle

- Server performs preflight checks on startup: `ollama` on PATH, `ollama serve`
  managed as subprocess, `nomic-embed-text` model available.
- Preflight failures are hard errors with actionable instructions.
- Clients auto-start the server if it's not running (via guru-core).

## Data Ownership

- `.guru/` directory in the project root holds all runtime state (db, socket, pid).
- `.guru/` is gitignored. It is pure runtime state, never version-controlled.
- `guru.json` in the project root holds indexing rules. It is version-controlled.

## Configuration

- Rule-based JSON config: each rule has `ruleName`, `match.glob`, optional `exclude`,
  `labels`, and `chunking` overrides.
- Resolution chain: `./guru.json` > `./.guru/config.json` > `~/.config/guru/config.json`.
- Merge by `ruleName`: local rules with same name fully replace global. New names appended.
- No config anywhere -> hardcoded default: index all `**/*.md`.

## Ingestion

- Document parsers implement a pluggable ingestion protocol (abstract base).
- Markdown is the first and only MVP parser (LlamaIndex MarkdownNodeParser +
  HierarchicalNodeParser + python-frontmatter).
- New formats are added by implementing the same interface. No core changes required.

## MCP

- stdio transport only (MVP). Universal across Claude Code, Cursor, Continue.dev.
- MCP tools map 1:1 to REST API endpoints. The MCP server contains zero business logic.
- MCP process inherits working directory from the agent for automatic project discovery.

## CLI

- `guru` with no arguments launches the Textual TUI.
- All commands except `guru init` trigger server auto-start.
- `guru init` creates `.guru/` and optionally `guru.json` with defaults.

## Language & Runtime

- Python-only codebase. Single language, single toolchain.
- Requires Python >= 3.13.
- Managed via uv workspaces.
- External runtime dependency: Ollama (installed separately).

## Methodology: Spec-Driven

- All major features must have BDD feature specs (Gherkin) as acceptance criteria.
- All REST API endpoints must have typed Pydantic request/response models producing
  a complete OpenAPI specification.
- Feature files (`tests/e2e/features/*.feature`) are part of the specification.
- Design specs and ADRs live in `docs/`.
