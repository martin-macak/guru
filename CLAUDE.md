# Guru Project Instructions

## What is this project?

Guru is a local-first knowledge-base manager that indexes documents in a git repo and
serves them to AI agents via RAG over MCP. It runs entirely on a developer's MacBook
with no cloud dependencies.

## Methodology: Spec-Driven Development

Everything is driven by specifications:
- **ARCHITECTURE.md** — architecture constitution. Non-breakable rules. If code
  contradicts it, the code is wrong. Read it before making any changes.
- **BDD feature files** (`tests/e2e/features/*.feature`) — acceptance criteria and
  scenarios. All major features MUST have corresponding Gherkin specs. Feature files
  are part of the specification, not just tests.
- **OpenAPI** — all REST API endpoints must have typed request/response models so
  FastAPI auto-generates a complete OpenAPI spec at `/openapi.json`. Use `response_model`
  on every endpoint.
- **Design specs** (`docs/superpowers/specs/`) — architectural decisions and designs.

When adding a feature: write the BDD feature file first, then implement.

## Architecture

Read ARCHITECTURE.md before making any changes. It is the **architecture constitution** —
every statement in it is a fact and a non-breakable rule. If code contradicts
ARCHITECTURE.md, the code is wrong. If a proposed change conflicts with ARCHITECTURE.md,
the change must be rejected or the constitution must be amended first.

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
guru-server -> guru-core (shared types only)
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
- behave (BDD e2e testing)
- pydantic (shared types, API schemas)

## Commands

```bash
uv sync --all-packages          # install all workspace packages
uv run guru                     # run CLI (launches TUI with no args)
uv run guru-server              # run server directly
uv run guru-mcp                 # run MCP server (stdio)
```

## Distribution

Guru is distributed via a PEP 503 simple index on GitHub Pages.
Build backend is `hatchling` + `uv-dynamic-versioning` (version from git tags).

```bash
uv tool install guru --extra-index-url https://martinmacak.github.io/guru/simple/
```

### Releasing

```bash
git tag v0.2.0
git push --tags
# CI builds wheels, creates GitHub Release, deploys to Pages index
```

### Build locally

```bash
uv build                                 # build root meta-package
uv build --directory packages/guru-core  # build single package
```

## Testing

```bash
uv run pytest                            # run unit + integration tests (serial, fast)
uv run pytest -n auto                   # run parallel (opt-in, useful when test count grows)
uv run pytest packages/guru-core/        # run guru-core tests only
uv run pytest packages/guru-server/      # run guru-server tests only
uv run pytest tests/                     # run integration tests
uv run pytest --tb=short -q              # quick summary
uv run behave tests/e2e/features/        # run BDD e2e tests (serial)
./scripts/run-behave-parallel.sh         # run BDD e2e tests (parallel, one process per feature)
```

### Test types
- **Unit tests** (pytest) — per-package under `packages/*/tests/`
- **Integration tests** (pytest) — `tests/test_integration.py`, mocked embedder
- **BDD e2e** (behave) — `tests/e2e/features/*.feature`, real server on UDS
  - `knowledge_base.feature` — CLI workflow with mocked embeddings (fast)
  - `mcp_tools.feature` — MCP protocol tools via FastMCP in-memory Client
  - `semantic_search.feature` (`@real_ollama`) — real Ollama embeddings, verifies
    semantic retrieval accuracy and config-driven labeling

### Conventions
- All major features must have BDD feature specs before implementation
- Feature files are acceptance criteria — they are part of the specification
- `@real_ollama` tag marks tests requiring a running Ollama instance
- pytest `@pytest.mark.slow` tests are skipped by default (run with `-m slow`)

## CI (GitHub Actions)

- `ci.yml` — unit tests per-package (skip if unchanged), e2e behind `require-e2e-tests` label
- `claude-code-review.yml` — Claude review behind `require-claude-review` label
- `claude.yml` — @claude mentions in PR comments

## Design Docs

All design documents live under `docs/`, organized by type:
- `docs/` — ADRs and top-level research (e.g. `INIT.md`)
- `docs/superpowers/specs/` — design specs, named `YYYY-MM-DD-<topic>-design.md`
- `docs/superpowers/plans/` — implementation plans, named `YYYY-MM-DD-<topic>.md`

## Gotchas

- macOS AF_UNIX socket paths have a 104-byte limit. Use short paths under `/tmp`
  for test fixtures that create UDS sockets.
- `fnmatch` does not support `**` recursive globs. Use `Path.glob()` instead.
- `PurePosixPath.match()` doesn't match `**` in the middle of patterns (e.g.
  `docs/**/*.md`). Use `Path.glob()` for recursive matching.
- LlamaIndex `MarkdownNodeParser` stores header info in a `header_path` key
  (slash-delimited), not `Header_1`/`Header_2` keys.
- uv workspace packages need `[tool.uv.sources]` with `package = { workspace = true }`
  for inter-package dependencies.
- Root `pyproject.toml` needs `addopts = "--import-mode=importlib"` for pytest to
  collect tests across multiple packages without `tests` package name collisions.
- pytest-xdist `-n auto` adds ~26s fork overhead — don't enable by default until
  the test suite is large enough to benefit. Keep serial, pass `-n auto` explicitly.
- MCP e2e tests patch `guru_mcp.server._get_client` to point at the test server.
  The MCP protocol layer (Client -> FastMCP -> CallToolRequest) is fully exercised.
- behave features run one server per feature (via `before_feature` hook) — features
  are fully independent and safe to parallelize.
