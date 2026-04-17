# Architecture Constitution

This document contains non-breakable rules and decisions that govern the guru project.
Everything in this document is a fact. Anything in contradiction must be assessed as a
potential bug or error and questioned.

---

## Core Principle

Guru is a **local-first, privacy-respecting** knowledge-base manager. No data leaves
the developer's machine. There are zero cloud dependencies.

## Architecture: Server-Centric

- **guru-server** owns all **per-project** state: LanceDB, Ollama, indexing.
- **guru-mcp** and **guru-cli** are stateless thin clients that call the server's REST API.
- No component other than guru-server may access LanceDB or Ollama directly.
- Machine-wide shared services (currently the optional graph plugin) are owned by their dedicated daemons — not by guru-server. See `## Graph Plugin` below.

## Transport: Unix Domain Sockets

- Server listens on `.guru/guru.sock` (HTTP over UDS).
- No TCP ports are used for inter-component communication.
- **Exception:** third-party backends (currently Neo4j, used by the optional graph plugin) may bind to a loopback-only TCP port. `guru-graph` is responsible for picking a free port dynamically, recording it in state, and restricting exposure to `127.0.0.1`. Bolt traffic never leaves the graph daemon's process boundary.
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
- `guru-server` depends on `guru-core` for shared types only. No other internal dependency.
- `guru-core` is a lightweight SDK: `httpx` + shared types. No heavy dependencies.
- guru-core is the canonical source of truth for all shared Pydantic models.
  Do not duplicate types across packages.

## Server Lifecycle

- Server performs preflight checks on startup: `ollama` on PATH, `ollama serve`
  managed as subprocess, `nomic-embed-text` model available.
- Preflight failures are hard errors with actionable instructions.
- Clients auto-start the server if it's not running (via guru-core).

## Data Ownership

- `.guru/` directory in the project root holds per-project runtime state (db, socket, pid, manifest). Each worktree has its own `.guru/`.
- `.guru/` is gitignored. It is pure runtime state, never version-controlled.
- `.guru.json` (preferred) or legacy `guru.json` in the project root holds indexing rules. It is version-controlled.
- The **embedding cache** lives at the OS-standard user cache directory (`$XDG_CACHE_HOME/guru/embeddings.db` on Linux, `~/Library/Caches/guru/embeddings.db` on macOS). It is a content-addressed optimization, not state: every entry is derivable from the chunks it caches, so deleting the cache is always safe — it only costs re-embedding time. The cache is shared across all guru projects and worktrees on the machine, keyed by `sha256(chunk_text) + model_name`.

## Configuration

- JSON config with a top-level `{ "version": 1, "rules": [...] }` object. Each rule has `ruleName`, `match.glob`, optional `exclude`, `labels`, and `chunking` overrides.
- The legacy flat-array format (`[ { "ruleName": ..., ... } ]`) is still read and auto-wrapped to `{ "version": 1, "rules": <array> }`. The `guru init` command and any future write path emit the object format.
- Resolution chain: `./.guru.json` > `./guru.json` > `./.guru/config.json` > `~/.config/guru/config.json`.
- Merge by `ruleName`: local rules with same name fully replace global. New names appended.
- No config anywhere → hardcoded default: index all `**/*.md`.

## Ingestion

- Document parsers implement a pluggable ingestion protocol (abstract base).
- Markdown is the first and only MVP parser (LlamaIndex MarkdownNodeParser +
  HierarchicalNodeParser + python-frontmatter).
- New formats are added by implementing the same interface. No core changes required.
- **Gitignore-aware discovery:** when the project root is inside a git repository, file discovery respects `.gitignore` via `git ls-files --cached --others --exclude-standard`. Gitignored paths are never indexed, regardless of whether they match the user's rule globs. Non-git projects fall back to pure glob discovery.

## MCP

- stdio transport only (MVP). Universal across Claude Code, Cursor, Continue.dev.
- MCP tools map 1:1 to REST API endpoints. The MCP server contains zero business logic.
- MCP process inherits working directory from the agent for automatic project discovery.
- **Developer-facing endpoint exception:** REST endpoints whose sole audience is the human developer (e.g. embedding cache management at `GET/DELETE /cache`, `POST /cache/prune`) are **not** exposed as MCP tools. Agents have no legitimate use for cache invalidation or pruning, so these operations are deliberately excluded from the MCP tool surface. The 1:1 mapping rule applies to endpoints an agent would call in normal operation (search, document read, status).

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

## Graph Plugin (optional)

- An optional `guru-graph` package ships in the workspace as a peer of `guru-server`. It is **disabled by default**; users enable it via `~/.config/guru/config.json → graph.enabled = true`.
- When enabled, a single machine-wide daemon is lazy-started by any guru-server. It owns a Neo4j Community subprocess. All guru-servers on the machine share it.
- The graph is strictly an augmentation. When the graph is disabled, unreachable, or failing, guru-server MUST continue to serve the user with reduced accuracy; graph failures never propagate to the end user.
- Clients never talk to Neo4j directly — only to `guru-graph` over UDS. Protocol and schema versions are negotiated per `docs/superpowers/specs/2026-04-17-graph-plugin-design.md` §Schema, versioning & compatibility.
