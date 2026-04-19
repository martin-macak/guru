# Guru Project Instructions

## Agent Instructions Layout

- Shared agent instructions live in `.agents/AGENTS.md`. This file is the single source
  of truth for the repository.
- Root `AGENTS.md` is a symlink to `.agents/AGENTS.md` so agent tooling that expects the
  standard file still works.
- Root `CLAUDE.md` is a thin Claude Code compatibility shim that imports `@AGENTS.md`.
- Keep shared instructions agent-agnostic here. Keep Claude Code runtime integration in
  `.claude/`.

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

This is a uv workspace monorepo with five packages under `packages/`:

- **guru-core**: Shared client SDK (discovery, auto-start, HTTP-over-UDS client, types, `GraphClient`)
- **guru-server**: FastAPI daemon that owns all **per-project** state (LanceDB, Ollama, ingestion)
- **guru-mcp**: MCP protocol adapter (thin client, FastMCP, stdio)
- **guru-cli**: CLI (click) + TUI (Textual)
- **guru-graph**: Optional machine-wide graph plugin daemon (FastAPI-over-UDS, Neo4j backend). Enabled by default; opt-out via `graph.enabled=false` in config. See `ARCHITECTURE.md` → Graph Plugin.

## Key Rules

- guru-server is the ONLY component that accesses LanceDB or Ollama
- guru-graph is the ONLY component that accesses Neo4j
- guru-mcp and guru-cli are thin clients — they talk to the server via guru-core
- Transport is HTTP over Unix domain socket at `.guru/guru.sock` (guru-server) and `$GURU_GRAPH_HOME/graph.sock` (guru-graph). Neo4j's Bolt port is an exception (loopback TCP only); see ARCHITECTURE.md.
- `.guru/` is runtime state, always gitignored
- `guru.json` is project config, version-controlled

## Dependencies Between Packages

```
guru-cli    -> guru-core
guru-mcp    -> guru-core
guru-server -> guru-core (shared types only)
guru-graph  -> guru-core
guru-server -> guru-graph (runtime-only, over UDS via GraphClient in guru-core)
guru-core   -> httpx
```

Do not add cross-dependencies that violate this graph.

## Tech Stack

- hatchling + uv-dynamic-versioning (build backend, version from git tags)
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
make help                       # list all available targets
make test                       # unit + integration tests (fast)
make test-all                   # unit + integration + e2e tests
make test-graph                 # graph plugin tests (requires Neo4j + GURU_REAL_NEO4J=1)
make build                      # build all 5 wheels into dist/
make lint                       # check code style
make fmt                        # auto-fix + format
make dev                        # run guru-server-dev + guru-web dev together
make dev-server                 # run guru-server-dev only (hot-reload, TCP-only)
make dev-web                    # run guru-web Vite dev server (proxies to dev-server)
```

## Code Quality

- Ruff is the linter and formatter. Config is in root `pyproject.toml`.
- `make lint` — check only (ruff check + ruff format --check)
- `make fmt` or `make format` — auto-fix + format (matches pre-commit)
- pre-commit hooks run ruff on every commit. Run `make format` before committing.
- Ruff rules: E, W, F, I, UP, B, SIM, RUF. Line length 99.

## GitHub Issues

When asked to track a bug, file a defect, or create an enhancement issue, agents
**MUST** comply with the project's issue-creation rules:

1. **Always use the correct template.** Blank issues are disabled. Two templates exist:
   - **Bug Report** (`bug_report`) — for unexpected behaviour, crashes, or wrong output.
   - **Enhancement** (`enhancement`) — for new features or improvements.

2. **Required fields for Bug Reports:**
   - `version` — the Guru version where the bug was observed. Must be a semver string
     (e.g. `0.3.1`, `1.0.0`, `2.1.0-alpha.1`). Obtain with `uv run guru --version` or
     `dunamai from git`. This field is mandatory; do not leave it blank or use "unknown".
   - `component` — select the affected package from the dropdown
     (`guru-server`, `guru-mcp`, `guru-cli / TUI`, `guru-core`, `guru-graph`, `Other / Unknown`).
   - `description`, `steps`, `expected`, `actual` — all required.

3. **Required fields for Enhancements:**
   - `component` — which package/area the enhancement targets.
   - `problem` — the motivation or pain point.
   - `solution` — the proposed change.

4. **Title format** — follow the project naming convention: `<type>: <description>`.
   - Bug issues: `fix: <short description>` (e.g. `fix: search returns empty after re-index`)
   - Enhancement issues: `feat: <short description>` (e.g. `feat: add PDF ingestion support`)

5. When creating issues via the GitHub API or CLI, supply all required fields explicitly.
   Do not skip or omit required fields. If a required field value is genuinely unknown,
   state that in the field rather than leaving it empty.

## Naming Conventions

Always follow naming conventions for GitHub PRs, Issues, and git branches:

**Format:** `<type>: <description>`

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `chore`: Maintenance tasks (dependencies, tooling, etc.)
- `refactor`: Code refactoring without behavior change
- `test`: Adding or updating tests
- `perf`: Performance improvements
- `ci`: CI/CD changes

**Examples:**
- PR/Issue: `docs: Update agent instructions`
- Branch: `feat/add-user-authentication`
- PR/Issue: `fix: Handle null pointer in auth middleware`
- Branch: `docs/update-installation-guide`

## Tooling

- `mise.toml` manages Python and pre-commit versions (mise tool version manager)
- `pre-commit install` to set up git hooks after cloning
- Claude Code hooks (`.claude/settings.json`) auto-run `ruff check --fix` + `ruff format`
  on every Python file after Edit/Write — no manual formatting needed
- Agents working inside a guru-managed project should use the
  `guru-knowledge-base` skill shipped by `guru init` at
  `.claude/skills/guru-knowledge-base/`.

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
  - `graph_plugin.feature` (partly `@real_neo4j`) — optional graph daemon
    lifecycle, opt-in/opt-out, protocol versioning, KB registration
  - `graph_cli_reads.feature` (partly `@real_neo4j`) — `guru graph {kbs, kb,
    links, query}` read-only CLI subcommands, including the never-expose-writes
    invariant and the `daemon: unreachable` error path

### Conventions
- All major features must have BDD feature specs before implementation
- Feature files are acceptance criteria — they are part of the specification
- `@real_ollama` tag marks tests requiring a running Ollama instance
- `@real_neo4j` tag marks tests requiring a running Neo4j. Skipped unless
  `GURU_REAL_NEO4J=1`. CI provides one via a `neo4j:5` service container.
  For local dev: `./scripts/start-test-neo4j.sh` + `GURU_NEO4J_BOLT_URI=bolt://127.0.0.1:17687`.
- pytest `@pytest.mark.slow` tests are skipped by default (run with `-m slow`)

## CI (GitHub Actions)

- `ci.yml` — unit tests per-package (skip if unchanged), e2e behind `require-e2e-tests` label
- `release.yml` — builds and publishes wheels on tag push, deploys to GitHub Pages index
- `claude-code-review.yml` — Claude review behind `require-claude-review` label
- `claude.yml` — @claude mentions in PR comments
- `copilot-setup-steps.yml` — shared setup steps for GitHub Copilot workflows

## Design Docs

All design documents live under `docs/`, organized by type:
- `docs/` — ADRs and top-level research
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
- `uv_build` does not support dynamic versioning (astral-sh/uv#14946). Use `hatchling`.
- `uv-dynamic-versioning` requires `hatchling`, not `uv_build` as build backend.
- When `"dependencies"` is in `dynamic = [...]`, ALL deps (inter-package + external)
  must go in `[tool.hatch.metadata.hooks.uv-dynamic-versioning]`, not `[project]`.
- `uv build --directory <pkg> --out-dir dist/` resolves `dist/` relative to the
  package dir, not cwd. Use absolute paths: `--out-dir "$(pwd)/dist/"`.
- pre-commit uses its own ruff install (from the hook repo), not the project's.
  The hook's ruff version may differ — keep `.pre-commit-config.yaml` rev in sync.
