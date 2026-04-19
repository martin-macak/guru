# Contributing to Guru

## Reporting Issues

**Issue templates are mandatory.** Blank issues are disabled. Always use the correct template:

| Template | When to use | Required fields |
|---|---|---|
| **Bug Report** | Unexpected behaviour, crashes, wrong output | Version (semver, e.g. `0.3.1`) · Component · Steps · Expected/Actual |
| **Enhancement** | New feature request or improvement | Component · Problem/Motivation · Proposed Solution |

Get your version with `uv run guru --version` or `dunamai from git`.  
Version strings must follow semver — this matches the `dunamai`/`uv-dynamic-versioning` output used in CI.

Issue titles must follow the naming convention: `<type>: <description>` (e.g. `fix: search returns empty on re-index`).

## Development setup

```bash
git clone https://github.com/martin-macak/guru.git
cd guru
uv sync --all-packages
```

## Agent Instructions

Shared project instructions for coding agents live in [`.agents/AGENTS.md`](.agents/AGENTS.md).
Root [`AGENTS.md`](AGENTS.md) is a compatibility symlink, and root [`CLAUDE.md`](CLAUDE.md)
imports `@AGENTS.md` so Claude Code uses the same instructions.

## Running tests

```bash
uv run pytest                            # unit + integration tests
uv run pytest packages/guru-core/        # guru-core tests only
uv run pytest packages/guru-server/      # guru-server tests only
uv run pytest packages/guru-mcp/         # guru-mcp tests only
uv run pytest packages/guru-cli/         # guru-cli tests only
uv run pytest -n auto                    # parallel (opt-in)
uv run behave tests/e2e/features/        # BDD e2e tests
./scripts/run-behave-parallel.sh         # e2e tests in parallel
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

## Package dependencies

```
guru (meta-package)
├── guru-core     (pydantic, httpx)
├── guru-server   (guru-core, fastapi, lancedb, llama-index, ollama)
├── guru-mcp      (guru-core, fastmcp)
└── guru-cli      (guru-core, click, textual)
```

## Releasing

Releases are automated via CI. To publish a new version:

```bash
git tag v0.2.0
git push --tags
```

CI will build all wheels, create a GitHub Release, and deploy to the
GitHub Pages package index automatically.

## CI

- `ci.yml` — unit tests per-package (skip if unchanged), e2e behind `require-e2e-tests` label
- `release.yml` — builds and publishes on tag push
- `claude-code-review.yml` — Claude review behind `require-claude-review` label
- `claude.yml` — @claude mentions in PR comments
