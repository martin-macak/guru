# Guru Packaging & Distribution Design

## Overview

Distribute Guru as a `uv tool install`-able package via a PEP 503 simple Python
index hosted on GitHub Pages. Users install with a single command, run `guru init`
in their markdown repo, and start using Guru with their AI agent immediately.

**Target audience:** Open-source developers using AI agents with MCP support.
**Platforms:** macOS and Linux.

## Install UX

```bash
# Install
uv tool install guru --extra-index-url https://martinmacak.github.io/guru/simple/

# Set up a repo
cd my-markdown-repo
guru init

# Upgrade
uv tool upgrade guru --extra-index-url https://martinmacak.github.io/guru/simple/

# Uninstall
uv tool uninstall guru
```

## 1. Package Structure

### Meta-package

The root `guru` package becomes a meta-package with no code or console scripts.
It declares dependencies on all sub-packages:

```toml
[project]
name = "guru"
dynamic = ["version", "dependencies"]
description = "Local-first knowledge base manager with MCP interface"
requires-python = ">=3.13"

[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "uv-dynamic-versioning"

[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    "guru-core=={{ version }}",
    "guru-server=={{ version }}",
    "guru-mcp=={{ version }}",
    "guru-cli=={{ version }}",
]

[tool.uv-dynamic-versioning]
vcs = "git"
style = "pep440"
bump = true
```

The `{{ version }}` placeholders are substituted at build time by
`uv-dynamic-versioning` from the git tag.

### Console scripts

Scripts remain defined in their respective sub-packages — `uv tool install` exposes
all of them:

| Script | Package | Entry point |
|--------|---------|-------------|
| `guru` | guru-cli | `guru_cli.cli:cli` |
| `guru-server` | guru-server | `guru_server.main:main` |
| `guru-mcp` | guru-mcp | `guru_mcp.server:main` |

### Inter-package dependencies

All inter-package dependencies use exact version pins (`=={{ version }}`),
substituted at build time via `[tool.hatch.metadata.hooks.uv-dynamic-versioning]`.
This guarantees version consistency:

- `guru` depends on `guru-core`, `guru-server`, `guru-mcp`, `guru-cli`
- `guru-server` depends on `guru-core`
- `guru-mcp` depends on `guru-core`
- `guru-cli` depends on `guru-core`

Each of these is declared in the respective package's
`[tool.hatch.metadata.hooks.uv-dynamic-versioning] dependencies` with
`=={{ version }}` pins. Packages that have inter-package deps must list
`"dependencies"` in `dynamic = [...]`.

## 2. Versioning

### Strategy: lockstep with dunamai

All packages share the same version, derived automatically from git tags using
`uv-dynamic-versioning` (which uses dunamai under the hood).

**Changes to all 5 `pyproject.toml` files:**
- Switch build backend from `uv_build` to `hatchling`
- Add `uv-dynamic-versioning` to build-system requires
- Remove `version = "0.1.0"`
- Add `dynamic = ["version"]` (and `"dependencies"` for packages with inter-package deps)
- Add `[tool.hatch.version]`, `[tool.uv-dynamic-versioning]` configuration
- Add `[tool.hatch.metadata.hooks.uv-dynamic-versioning]` for inter-package deps

**Version derivation:**
- Tag `v0.2.0` → version `0.2.0` for all packages
- Untagged commits get a dev version (e.g., `0.2.0.dev3+gabcdef`)

**Release workflow:**
```bash
git tag v0.2.0
git push --tags
# CI handles everything from here
```

### Build backend: hatchling + uv-dynamic-versioning

All packages switch from `uv_build` to `hatchling`. The `uv_build` backend does
not support dynamic versioning ([astral-sh/uv#14946](https://github.com/astral-sh/uv/issues/14946)).
`hatchling` is the [recommended alternative](https://docs.astral.sh/uv/concepts/build-backend/)
for projects needing more flexibility. This switch has zero impact on the dev
workflow — `uv sync`, `uv run`, `uv build` all work identically with `hatchling`.

**Build system (all 5 packages):**
```toml
[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]
build-backend = "hatchling.build"
```

**Version source (all 5 packages):**
```toml
[tool.hatch.version]
source = "uv-dynamic-versioning"

[tool.uv-dynamic-versioning]
vcs = "git"
style = "pep440"
bump = true
```

**Dynamic dependencies (packages with inter-package deps):**

For packages with inter-package deps, both dynamic and static deps are declared
in the metadata hook. When `"dependencies"` is listed in `dynamic = [...]`, the
hook's `dependencies` list **replaces** `project.dependencies` entirely. Therefore
all dependencies (both inter-package and external) must be listed in the hook.

Example for `guru-server`:
```toml
[project]
name = "guru-server"
dynamic = ["version", "dependencies"]

[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    "guru-core=={{ version }}",
    "httpx>=0.28",
    "pydantic>=2.0",
    "llama-index-core>=0.14",
    "python-frontmatter>=1.1",
    "lancedb>=0.27",
    "pandas>=2.0",
    "fastapi>=0.115",
    "uvicorn>=0.34",
]
```

The `{{ version }}` placeholder is substituted at build time. Static deps like
`fastapi>=0.115` pass through unchanged.

For `guru-core` (no inter-package deps), only `dynamic = ["version"]` is needed
and dependencies stay in `[project]` as normal.

**Version derivation:**
- Tag `v0.2.0` → version `0.2.0`
- Pattern: default dunamai pattern matching `v*` tags
- Style: PEP 440

## 3. GitHub Pages Simple Index

### Structure

A PEP 503-compliant simple repository index on the `gh-pages` branch:

```
simple/
├── index.html                  # root: links to each package
├── guru/
│   └── index.html              # links to guru wheels
├── guru-core/
│   └── index.html              # links to guru-core wheels
├── guru-server/
│   └── index.html              # links to guru-server wheels
├── guru-mcp/
│   └── index.html              # links to guru-mcp wheels
└── guru-cli/
    └── index.html              # links to guru-cli wheels
wheels/
├── guru-0.1.0-py3-none-any.whl
├── guru_core-0.1.0-py3-none-any.whl
├── guru_server-0.1.0-py3-none-any.whl
├── guru_mcp-0.1.0-py3-none-any.whl
└── guru_cli-0.1.0-py3-none-any.whl
```

### Index generation

A script (`scripts/generate-index.py`) scans the `wheels/` directory and generates
PEP 503-compliant HTML:

- Root `simple/index.html`: one `<a>` per package name
- Per-package `simple/<name>/index.html`: one `<a href>` per wheel file

Old versions remain available — new releases add new wheels and regenerate the
index HTML files.

### URL

```
https://martinmacak.github.io/guru/simple/
```

PyPI remains the default index for transitive dependencies (FastAPI, LanceDB,
pydantic, etc.). Only `guru-*` packages are served from this index.

## 4. CI/CD Release Pipeline

### Workflow: `.github/workflows/release.yml`

**Trigger:** Push of tag matching `v*`

**Steps:**

1. **Checkout** source at the tagged commit
2. **Setup** Python 3.13 + uv
3. **Build wheels** for all 5 packages using `uv build`. Dynamic versioning
   derives version from the git tag automatically.
4. **Create GitHub Release** — attach all 5 wheels as release assets,
   auto-generate release notes from commits since last tag
5. **Deploy to GitHub Pages:**
   - Checkout `gh-pages` branch (create if first release)
   - Copy new wheels into `wheels/`
   - Run `scripts/generate-index.py` to regenerate `simple/*/index.html`
   - Commit and push to `gh-pages`

### First-time setup

- Enable GitHub Pages for the repo (source: `gh-pages` branch)
- The first release workflow run creates the `gh-pages` branch if it doesn't exist

### Tag format

Only stable `vX.Y.Z` tags trigger the pipeline. Pre-release tags are not supported
initially.

## 5. `guru init` Enhancements

`guru init` becomes the single setup command for new repos. It is idempotent —
running it twice is safe.

**Actions:**

1. **Create `.guru/` directory** (existing behavior)
2. **Create `guru.json`** with default indexing rules (existing behavior)
3. **Merge guru entry into `.mcp.json`** (new):
   - If `.mcp.json` exists: read, add `guru` under `mcpServers`, write back.
     Preserves existing entries.
   - If `.mcp.json` doesn't exist: create with guru entry only.
   - If `guru` already present in `.mcp.json`: skip with message.
   - Entry content: `{"command": "guru-mcp"}`
4. **Add `.guru/` to `.gitignore`** (new):
   - If `.gitignore` exists: append `.guru/` if not already present.
   - If `.gitignore` doesn't exist: create with `.guru/`.

**Output:**
```
Created .guru/
Created guru.json with default rules
Added guru to .mcp.json
Added .guru/ to .gitignore
```

Skipped steps print accordingly (e.g., "guru.json already exists, skipping").

## 6. Auto-start

`guru-mcp` auto-starts `guru-server` via `guru_core.autostart.ensure_server()`.
The current implementation uses `subprocess.Popen(["guru-server"], ...)`, which
finds `guru-server` on PATH. This works correctly with `uv tool install` because
all console scripts from the meta-package's dependencies are symlinked into the
same `~/.local/bin/` directory.

No changes needed to the auto-start mechanism.

## 7. Documentation

### README.md (rewrite for end users)

1. What is Guru (one paragraph)
2. Prerequisites (Python 3.13+, uv, Ollama, `ollama pull nomic-embed-text`)
3. Install (one-liner with `--extra-index-url`)
4. Quick Start (`guru init`, `guru index`, open AI agent)
5. Configuration (`guru.json` format, rules, labels, chunking)
6. Upgrade command
7. Uninstall command
8. Troubleshooting (common issues)

### CONTRIBUTING.md (new, for developers)

- Dev setup (`git clone`, `uv sync --all-packages`)
- Running tests (pytest, behave, parallel)
- Project structure and package boundaries
- Architecture overview (pointer to ARCHITECTURE.md)
- Release process (tag and push)

### License

A LICENSE file must be added before the first public release. Choice of license
is a prerequisite but outside the scope of this design.

## 8. Deliverables Summary

| Deliverable | Type | Description |
|-------------|------|-------------|
| Root `pyproject.toml` | Modify | Add sub-package dependencies, dynamic version |
| All 5 `pyproject.toml` | Modify | Switch to hatchling, dynamic versioning, exact inter-package pins |
| `scripts/generate-index.py` | New | PEP 503 index HTML generator |
| `.github/workflows/release.yml` | New | Tag-triggered build + publish pipeline |
| `guru init` in guru-cli | Modify | Add `.mcp.json` merge and `.gitignore` update |
| `README.md` | Rewrite | User-facing install and usage guide |
| `CONTRIBUTING.md` | New | Developer guide (current README content) |
| `LICENSE` | New | License file (prerequisite, choice TBD) |
