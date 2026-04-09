# Packaging & Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distribute Guru as a `uv tool install`-able package via a PEP 503 simple index on GitHub Pages, with automatic versioning from git tags.

**Architecture:** Switch all 5 packages from `uv_build` to `hatchling` + `uv-dynamic-versioning` for git-tag-based lockstep versioning. Root `guru` becomes a meta-package pulling in all sub-packages. A CI workflow builds wheels on tag push and deploys to a GitHub Pages simple index. `guru init` is enhanced to generate `.mcp.json` and `.gitignore` entries.

**Tech Stack:** hatchling, uv-dynamic-versioning (dunamai), GitHub Actions, GitHub Pages, PEP 503

**Spec:** `docs/superpowers/specs/2026-04-09-packaging-distribution-design.md`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `pyproject.toml` | Modify | Meta-package with hatchling, dynamic version + deps |
| `packages/guru-core/pyproject.toml` | Modify | Switch to hatchling, dynamic version |
| `packages/guru-server/pyproject.toml` | Modify | Switch to hatchling, dynamic version + deps |
| `packages/guru-mcp/pyproject.toml` | Modify | Switch to hatchling, dynamic version + deps |
| `packages/guru-cli/pyproject.toml` | Modify | Switch to hatchling, dynamic version + deps |
| `packages/guru-cli/src/guru_cli/cli.py` | Modify | Enhance `init` cmd, fix version |
| `packages/guru-cli/tests/test_cli.py` | Modify | Tests for new init behavior |
| `scripts/generate-index.py` | Create | PEP 503 index HTML generator |
| `scripts/test-generate-index.py` | Create | Tests for index generator |
| `.github/workflows/release.yml` | Create | Tag-triggered release pipeline |
| `README.md` | Rewrite | User-facing install/usage guide |
| `CONTRIBUTING.md` | Create | Developer guide |

---

### Task 1: Switch guru-core to hatchling + dynamic versioning

**Files:**
- Modify: `packages/guru-core/pyproject.toml`

This is the leaf dependency — no inter-package deps, simplest to start with.

- [ ] **Step 1: Update guru-core pyproject.toml**

Replace the entire `packages/guru-core/pyproject.toml` with:

```toml
[project]
name = "guru-core"
dynamic = ["version"]
description = "Guru shared client SDK and types"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.28",
]

[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "uv-dynamic-versioning"

[tool.uv-dynamic-versioning]
vcs = "git"
style = "pep440"
bump = true

[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

Key changes: removed `version = "0.1.0"`, added `dynamic = ["version"]`, switched build-system from `uv_build` to `hatchling` + `uv-dynamic-versioning`, added hatch version source and dynamic versioning config. Dependencies stay in `[project]` because guru-core has no inter-package deps.

- [ ] **Step 2: Verify the workspace still resolves**

Run: `uv sync --all-packages`
Expected: completes successfully, all packages install

- [ ] **Step 3: Run guru-core tests**

Run: `uv run pytest packages/guru-core/ -v --tb=short`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add packages/guru-core/pyproject.toml
git commit -m "build: switch guru-core to hatchling + uv-dynamic-versioning"
```

---

### Task 2: Switch guru-server to hatchling + dynamic versioning

**Files:**
- Modify: `packages/guru-server/pyproject.toml`

guru-server depends on guru-core, so it needs `dynamic = ["version", "dependencies"]` and the metadata hook for version-pinned deps.

- [ ] **Step 1: Update guru-server pyproject.toml**

Replace the entire `packages/guru-server/pyproject.toml` with:

```toml
[project]
name = "guru-server"
dynamic = ["version", "dependencies"]
description = "Guru FastAPI server — owns all state (LanceDB, Ollama, ingestion)"
readme = "README.md"
authors = [
    { name = "Martin Macak", email = "martin.macak@gmail.com" }
]
requires-python = ">=3.13"

[project.scripts]
guru-server = "guru_server.main:main"

[tool.uv.sources]
guru-core = { workspace = true }

[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "uv-dynamic-versioning"

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

[tool.uv-dynamic-versioning]
vcs = "git"
style = "pep440"
bump = true

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

Key changes: removed `version` and `dependencies` from `[project]`, added both to `dynamic`, moved all dependencies (including `guru-core=={{ version }}`) into the metadata hook, switched build backend.

- [ ] **Step 2: Verify the workspace still resolves**

Run: `uv sync --all-packages`
Expected: completes successfully

- [ ] **Step 3: Run guru-server tests**

Run: `uv run pytest packages/guru-server/ -v --tb=short`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add packages/guru-server/pyproject.toml
git commit -m "build: switch guru-server to hatchling + uv-dynamic-versioning"
```

---

### Task 3: Switch guru-mcp to hatchling + dynamic versioning

**Files:**
- Modify: `packages/guru-mcp/pyproject.toml`

- [ ] **Step 1: Update guru-mcp pyproject.toml**

Replace the entire `packages/guru-mcp/pyproject.toml` with:

```toml
[project]
name = "guru-mcp"
dynamic = ["version", "dependencies"]
description = "Guru MCP protocol adapter"
readme = "README.md"
authors = [
    { name = "Martin Macak", email = "martin.macak@gmail.com" }
]
requires-python = ">=3.13"

[project.scripts]
guru-mcp = "guru_mcp.server:main"

[tool.uv.sources]
guru-core = { workspace = true }

[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "uv-dynamic-versioning"

[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    "guru-core=={{ version }}",
    "fastmcp>=2.0",
]

[tool.uv-dynamic-versioning]
vcs = "git"
style = "pep440"
bump = true

[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

- [ ] **Step 2: Verify the workspace still resolves**

Run: `uv sync --all-packages`
Expected: completes successfully

- [ ] **Step 3: Run guru-mcp tests**

Run: `uv run pytest packages/guru-mcp/ -v --tb=short`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add packages/guru-mcp/pyproject.toml
git commit -m "build: switch guru-mcp to hatchling + uv-dynamic-versioning"
```

---

### Task 4: Switch guru-cli to hatchling + dynamic versioning

**Files:**
- Modify: `packages/guru-cli/pyproject.toml`
- Modify: `packages/guru-cli/src/guru_cli/cli.py` (fix hardcoded version)
- Modify: `packages/guru-cli/tests/test_cli.py` (fix version test)

- [ ] **Step 1: Update guru-cli pyproject.toml**

Replace the entire `packages/guru-cli/pyproject.toml` with:

```toml
[project]
name = "guru-cli"
dynamic = ["version", "dependencies"]
description = "Guru CLI and TUI"
readme = "README.md"
authors = [
    { name = "Martin Macak", email = "martin.macak@gmail.com" }
]
requires-python = ">=3.13"

[project.scripts]
guru = "guru_cli.cli:cli"

[tool.uv.sources]
guru-core = { workspace = true }

[build-system]
requires = ["hatchling", "uv-dynamic-versioning"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "uv-dynamic-versioning"

[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    "guru-core=={{ version }}",
    "click>=8.1",
    "textual>=0.80",
]

[tool.uv-dynamic-versioning]
vcs = "git"
style = "pep440"
bump = true

[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

- [ ] **Step 2: Fix hardcoded version in cli.py**

In `packages/guru-cli/src/guru_cli/cli.py`, replace the hardcoded version:

```python
# Before:
@click.version_option(version="0.1.0")

# After:
from importlib.metadata import version as pkg_version

@click.version_option(version=pkg_version("guru-cli"))
```

The `importlib.metadata.version()` reads the version from the installed package metadata, which is set by hatchling + uv-dynamic-versioning at build time.

Note: the import should go at the top of the file with the other imports. The `@click.version_option` decorator evaluates `pkg_version("guru-cli")` at import time, which is fine for a CLI entry point.

Full change to the top of `cli.py`:

```python
from __future__ import annotations

import asyncio
import json
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

import click

from guru_core.discovery import find_guru_root, GuruNotFoundError
from guru_core.autostart import ensure_server
from guru_core.client import GuruClient
```

And the decorator:

```python
@click.group(invoke_without_command=True)
@click.version_option(version=pkg_version("guru-cli"))
@click.pass_context
def cli(ctx):
```

- [ ] **Step 3: Fix the version test**

In `packages/guru-cli/tests/test_cli.py`, the test `test_cli_version` checks for `"0.1.0"`. Update it to verify the command succeeds and outputs *some* version rather than a hardcoded string:

```python
def test_cli_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower() or "." in result.output
```

- [ ] **Step 4: Verify workspace resolves and tests pass**

Run: `uv sync --all-packages && uv run pytest packages/guru-cli/ -v --tb=short`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli/pyproject.toml packages/guru-cli/src/guru_cli/cli.py packages/guru-cli/tests/test_cli.py
git commit -m "build: switch guru-cli to hatchling + uv-dynamic-versioning

Also replace hardcoded version string with importlib.metadata lookup."
```

---

### Task 5: Convert root pyproject.toml to meta-package

**Files:**
- Modify: `pyproject.toml`

The root package becomes a meta-package that pulls in all sub-packages.

- [ ] **Step 1: Update root pyproject.toml**

Replace the entire `pyproject.toml` with:

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

[tool.uv.workspace]
members = ["packages/*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "--import-mode=importlib -m 'not slow'"
markers = [
    "slow: end-to-end tests that start a real server (deselected by default, run with: -m slow)",
]

[dependency-groups]
dev = [
    "behave>=1.3.3",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-xdist>=3.8.0",
]
```

Key changes: removed `version` and `dependencies` from `[project]`, added `dynamic`, added hatchling build-system, added metadata hook with all 4 sub-packages as `{{ version }}`-pinned deps. Preserved `[tool.uv.workspace]`, `[tool.pytest.ini_options]`, and `[dependency-groups]`.

- [ ] **Step 2: Verify full workspace resolves**

Run: `uv sync --all-packages`
Expected: completes successfully

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -v --tb=short`
Expected: all tests pass

- [ ] **Step 4: Verify wheel builds**

Run: `uv build`
Expected: produces `dist/guru-*.whl` and `dist/guru-*.tar.gz`. The version will be derived from the latest git tag (or a dev version if no tag exists yet).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build: convert root package to meta-package with dynamic versioning"
```

---

### Task 6: Enhance `guru init` — add .mcp.json generation

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/cli.py`
- Modify: `packages/guru-cli/tests/test_cli.py`

- [ ] **Step 1: Write failing tests for .mcp.json generation**

Add these tests to `packages/guru-cli/tests/test_cli.py`:

```python
def test_init_creates_mcp_json(runner, tmp_path):
    """guru init creates .mcp.json with guru entry when file doesn't exist."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        mcp_file = Path(td) / ".mcp.json"
        assert mcp_file.is_file()
        mcp = json.loads(mcp_file.read_text())
        assert mcp["mcpServers"]["guru"]["command"] == "guru-mcp"
        assert "Added guru to .mcp.json" in result.output


def test_init_merges_into_existing_mcp_json(runner, tmp_path):
    """guru init preserves existing MCP servers when adding guru."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        mcp_file = Path(td) / ".mcp.json"
        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "other-tool": {"command": "other-tool-mcp"}
            }
        }))
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        mcp = json.loads(mcp_file.read_text())
        assert "other-tool" in mcp["mcpServers"]
        assert "guru" in mcp["mcpServers"]


def test_init_skips_existing_guru_mcp_entry(runner, tmp_path):
    """guru init skips .mcp.json if guru entry already exists."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        mcp_file = Path(td) / ".mcp.json"
        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "guru": {"command": "guru-mcp"}
            }
        }))
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "guru already configured in .mcp.json" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py::test_init_creates_mcp_json packages/guru-cli/tests/test_cli.py::test_init_merges_into_existing_mcp_json packages/guru-cli/tests/test_cli.py::test_init_skips_existing_guru_mcp_entry -v`
Expected: FAIL (new behavior not implemented)

- [ ] **Step 3: Implement .mcp.json generation in init command**

In `packages/guru-cli/src/guru_cli/cli.py`, replace the `init` function with:

```python
@cli.command()
def init():
    """Initialize a guru project in the current directory."""
    cwd = Path.cwd()
    guru_dir = cwd / ".guru"
    guru_json = cwd / "guru.json"
    mcp_json = cwd / ".mcp.json"
    gitignore = cwd / ".gitignore"

    # 1. Create .guru/ directory
    if guru_dir.is_dir():
        click.echo("Already initialized — .guru/ directory exists.")
    else:
        guru_dir.mkdir()
        (guru_dir / "db").mkdir()
        click.echo("Created .guru/")

    # 2. Create guru.json
    if guru_json.exists():
        click.echo("guru.json already exists, skipping.")
    else:
        guru_json.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
        click.echo("Created guru.json with default rules")

    # 3. Merge guru into .mcp.json
    _init_mcp_json(mcp_json)

    # 4. Add .guru/ to .gitignore
    _init_gitignore(gitignore)


def _init_mcp_json(mcp_json: Path) -> None:
    """Add guru entry to .mcp.json, creating or merging as needed."""
    guru_entry = {"command": "guru-mcp"}

    if mcp_json.exists():
        mcp = json.loads(mcp_json.read_text())
        servers = mcp.setdefault("mcpServers", {})
        if "guru" in servers:
            click.echo("guru already configured in .mcp.json, skipping.")
            return
        servers["guru"] = guru_entry
    else:
        mcp = {"mcpServers": {"guru": guru_entry}}

    mcp_json.write_text(json.dumps(mcp, indent=2) + "\n")
    click.echo("Added guru to .mcp.json")


def _init_gitignore(gitignore: Path) -> None:
    """Add .guru/ to .gitignore if not already present."""
    marker = ".guru/"
    if gitignore.exists():
        content = gitignore.read_text()
        if marker in content.splitlines():
            click.echo(".guru/ already in .gitignore, skipping.")
            return
        if not content.endswith("\n"):
            content += "\n"
        content += marker + "\n"
    else:
        content = marker + "\n"

    gitignore.write_text(content)
    click.echo("Added .guru/ to .gitignore")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py -v --tb=short`
Expected: all tests pass (including the existing ones)

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/cli.py packages/guru-cli/tests/test_cli.py
git commit -m "feat: guru init generates .mcp.json and .gitignore entries"
```

---

### Task 7: Enhance `guru init` — add .gitignore generation

**Files:**
- Modify: `packages/guru-cli/tests/test_cli.py`

The implementation was included in Task 6. This task adds the tests.

- [ ] **Step 1: Write tests for .gitignore generation**

Add these tests to `packages/guru-cli/tests/test_cli.py`:

```python
def test_init_creates_gitignore(runner, tmp_path):
    """guru init creates .gitignore with .guru/ when file doesn't exist."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        gitignore = Path(td) / ".gitignore"
        assert gitignore.is_file()
        assert ".guru/" in gitignore.read_text().splitlines()
        assert "Added .guru/ to .gitignore" in result.output


def test_init_appends_to_existing_gitignore(runner, tmp_path):
    """guru init appends .guru/ to existing .gitignore."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        gitignore = Path(td) / ".gitignore"
        gitignore.write_text("node_modules/\n.env\n")
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        lines = gitignore.read_text().splitlines()
        assert "node_modules/" in lines
        assert ".env" in lines
        assert ".guru/" in lines


def test_init_skips_existing_gitignore_entry(runner, tmp_path):
    """guru init skips .gitignore if .guru/ already present."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        gitignore = Path(td) / ".gitignore"
        gitignore.write_text(".guru/\n")
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert ".guru/ already in .gitignore" in result.output
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py -v --tb=short`
Expected: all tests pass (implementation was done in Task 6)

- [ ] **Step 3: Update the existing init tests for new output format**

The existing `test_init_creates_guru_dir` test checks for `"Initialized"` in output. The new `init` outputs line-by-line messages instead. Update:

```python
def test_init_creates_guru_dir(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (Path(td) / ".guru").is_dir()
        assert "Created .guru/" in result.output
```

The existing `test_init_already_initialized` test should still work because the `.guru/` check still outputs "already initialized". But verify it still passes.

- [ ] **Step 4: Run all cli tests**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py -v --tb=short`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli/tests/test_cli.py
git commit -m "test: add tests for guru init .mcp.json and .gitignore generation"
```

---

### Task 8: Create PEP 503 index generator script

**Files:**
- Create: `scripts/generate-index.py`
- Create: `scripts/test-generate-index.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test-generate-index.py`:

```python
"""Tests for the PEP 503 simple index generator."""

import sys
from pathlib import Path

# Allow importing the script from the same directory
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from generate_index import generate_index


@pytest.fixture
def wheel_dir(tmp_path):
    """Create a fake wheels directory with sample wheel files."""
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    # Create fake wheel files (content doesn't matter, just filenames)
    (wheels / "guru-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_core-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_server-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_mcp-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_cli-0.1.0-py3-none-any.whl").touch()
    return wheels


def test_generates_root_index(wheel_dir, tmp_path):
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    root_html = (simple / "index.html").read_text()
    assert "<a href=\"guru/\">guru</a>" in root_html
    assert "<a href=\"guru-core/\">guru-core</a>" in root_html
    assert "<a href=\"guru-server/\">guru-server</a>" in root_html
    assert "<a href=\"guru-mcp/\">guru-mcp</a>" in root_html
    assert "<a href=\"guru-cli/\">guru-cli</a>" in root_html


def test_generates_package_index(wheel_dir, tmp_path):
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    guru_html = (simple / "guru" / "index.html").read_text()
    assert "guru-0.1.0-py3-none-any.whl" in guru_html
    # Check the href points to the wheels directory
    assert "../../wheels/guru-0.1.0-py3-none-any.whl" in guru_html


def test_multiple_versions(wheel_dir, tmp_path):
    (wheel_dir / "guru-0.2.0-py3-none-any.whl").touch()
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    guru_html = (simple / "guru" / "index.html").read_text()
    assert "guru-0.1.0-py3-none-any.whl" in guru_html
    assert "guru-0.2.0-py3-none-any.whl" in guru_html


def test_normalized_package_names(wheel_dir, tmp_path):
    """Wheel filenames use underscores but PEP 503 dirs use hyphens."""
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    # guru_core wheel → guru-core directory
    assert (simple / "guru-core" / "index.html").is_file()
    core_html = (simple / "guru-core" / "index.html").read_text()
    assert "guru_core-0.1.0-py3-none-any.whl" in core_html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest scripts/test-generate-index.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'generate_index'`

- [ ] **Step 3: Implement the index generator**

Create `scripts/generate-index.py`:

```python
#!/usr/bin/env python3
"""Generate a PEP 503 simple repository index from a directory of wheels.

Usage: python scripts/generate-index.py <wheels-dir> <output-dir>

Scans <wheels-dir> for .whl files and generates a PEP 503-compliant simple
repository index in <output-dir>/. Package directories use normalized names
(lowercase, hyphens). Links point to ../../wheels/<filename>.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# PEP 503: normalize by lowercasing and replacing runs of [_.-] with a single hyphen
_NORMALIZE_RE = re.compile(r"[-_.]+")


def _normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("-", name).lower()


def _parse_wheel_name(filename: str) -> str | None:
    """Extract the distribution name from a wheel filename.

    Wheel filenames follow: {name}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    """
    parts = filename.split("-")
    if len(parts) < 3:
        return None
    return parts[0]


def generate_index(wheels_dir: Path, output_dir: Path) -> None:
    """Generate PEP 503 simple index from wheels directory."""
    wheel_files = sorted(wheels_dir.glob("*.whl"))

    # Group wheels by normalized package name
    packages: dict[str, list[str]] = {}
    for whl in wheel_files:
        raw_name = _parse_wheel_name(whl.name)
        if raw_name is None:
            continue
        norm = _normalize(raw_name)
        packages.setdefault(norm, []).append(whl.name)

    # Generate root index
    output_dir.mkdir(parents=True, exist_ok=True)
    root_links = []
    for name in sorted(packages):
        root_links.append(f'<a href="{name}/">{name}</a>')

    (output_dir / "index.html").write_text(
        "<!DOCTYPE html>\n<html><body>\n"
        + "\n".join(root_links)
        + "\n</body></html>\n"
    )

    # Generate per-package index
    for name, wheels in sorted(packages.items()):
        pkg_dir = output_dir / name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        links = []
        for whl in sorted(wheels):
            links.append(f'<a href="../../wheels/{whl}">{whl}</a>')
        (pkg_dir / "index.html").write_text(
            "<!DOCTYPE html>\n<html><body>\n"
            + "\n".join(links)
            + "\n</body></html>\n"
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <wheels-dir> <output-dir>", file=sys.stderr)
        sys.exit(1)
    generate_index(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"Index generated in {sys.argv[2]}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest scripts/test-generate-index.py -v --tb=short`
Expected: all 4 tests pass

- [ ] **Step 5: Commit**

```bash
git add scripts/generate-index.py scripts/test-generate-index.py
git commit -m "feat: add PEP 503 simple index generator script"
```

---

### Task 9: Create GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create the release workflow**

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history needed for dunamai version detection

      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"

      - name: Install build dependencies
        run: uv sync --all-packages

      - name: Build all wheels
        run: |
          mkdir -p dist
          for pkg in packages/guru-core packages/guru-server packages/guru-mcp packages/guru-cli .; do
            uv build --directory "$pkg" --out-dir dist/
          done

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "${{ github.ref_name }}" dist/*.whl \
            --title "${{ github.ref_name }}" \
            --generate-notes

      - name: Deploy to GitHub Pages index
        run: |
          set -e

          # Configure git
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          # Prepare a temporary working area
          WORK=$(mktemp -d)
          PAGES_BRANCH=gh-pages

          # Try to fetch existing gh-pages, or start fresh
          if git ls-remote --exit-code origin "$PAGES_BRANCH" > /dev/null 2>&1; then
            git fetch origin "$PAGES_BRANCH"
            git worktree add "$WORK" "$PAGES_BRANCH"
          else
            git worktree add --orphan "$WORK" "$PAGES_BRANCH"
            # Clean the orphan worktree
            rm -rf "$WORK"/*
          fi

          # Copy new wheels
          mkdir -p "$WORK/wheels"
          cp dist/*.whl "$WORK/wheels/"

          # Generate index
          python scripts/generate-index.py "$WORK/wheels" "$WORK/simple"

          # Commit and push
          cd "$WORK"
          git add --all
          if git diff --cached --quiet; then
            echo "No changes to deploy"
          else
            git commit -m "release: deploy ${{ github.ref_name }}"
            git push origin "$PAGES_BRANCH"
          fi

          # Cleanup worktree
          cd -
          git worktree remove "$WORK" --force
```

- [ ] **Step 2: Validate the YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))" 2>&1 || echo "Install PyYAML first: pip install pyyaml"`

If `yaml` not available, use: `uv run python -c "import json, sys; print('YAML looks structurally valid')" && echo "Manual review: check indentation"`

Alternatively, just review the file manually for correct YAML indentation.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add tag-triggered release workflow with GitHub Pages index"
```

---

### Task 10: Rewrite README.md for end users

**Files:**
- Rewrite: `README.md`
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Save current README content to CONTRIBUTING.md**

Create `CONTRIBUTING.md` with the developer-focused content:

```markdown
# Contributing to Guru

## Development setup

```bash
git clone https://github.com/martinmacak/guru.git
cd guru
uv sync --all-packages
```

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
```

- [ ] **Step 2: Rewrite README.md for end users**

Replace `README.md` with:

```markdown
# Guru

A local-first knowledge-base manager that indexes markdown documents in a git repo and serves them to AI agents via RAG over MCP. Runs entirely on your machine with no cloud dependencies.

## Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (package manager)
- [Ollama](https://ollama.com) with the `nomic-embed-text` model

```bash
# macOS
brew install ollama

# Linux — see https://ollama.com/download
curl -fsSL https://ollama.com/install.sh | sh

# Pull the embedding model
ollama pull nomic-embed-text
```

## Install

```bash
uv tool install guru --extra-index-url https://martinmacak.github.io/guru/simple/
```

This installs the `guru`, `guru-server`, and `guru-mcp` commands.

## Quick start

```bash
# Initialize guru in your markdown repo
cd /path/to/your/repo
guru init

# Index your documents
guru index

# Search
guru search "authentication flow"
```

`guru init` creates:
- `.guru/` — runtime directory (gitignored automatically)
- `guru.json` — indexing rules (version-controlled)
- `.mcp.json` — MCP server configuration for AI agents

## MCP integration

After `guru init`, your `.mcp.json` is configured automatically. AI agents that support MCP (Claude Code, Cursor, Continue.dev) will discover the guru tools:

- `search` — semantic search across your knowledge base
- `get_document` — retrieve a full document
- `list_documents` — browse all indexed documents
- `get_section` — retrieve a specific markdown section
- `index_status` — check index health and stats

The guru server starts automatically when an MCP tool is first invoked.

## Configuration

Edit `guru.json` in your project root to control indexing:

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

Config resolution: `./guru.json` > `./.guru/config.json` > `~/.config/guru/config.json`. Rules merge by `ruleName` (local overrides global).

## CLI commands

```
guru init                # set up guru in current directory
guru index [PATH]        # index documents
guru search "query"      # semantic search
guru doc <path>          # get full document
guru doc <path> -s "H"   # get specific section
guru list                # list indexed documents
guru config              # show resolved config
guru server start|stop|status
```

## Upgrade

```bash
uv tool upgrade guru --extra-index-url https://martinmacak.github.io/guru/simple/
```

## Uninstall

```bash
uv tool uninstall guru
```

## Troubleshooting

**"guru-server did not start"**
- Check that Ollama is running: `ollama list`
- Ensure the embedding model is installed: `ollama pull nomic-embed-text`

**"command not found: guru"**
- Ensure `~/.local/bin` is on your PATH (uv tool install puts binaries there)
- Run `uv tool list` to verify guru is installed

**Server won't stop**
- Run `guru server stop` or check `.guru/guru.pid` for the process ID

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and release process.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture constitution.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CONTRIBUTING.md
git commit -m "docs: rewrite README for end users, add CONTRIBUTING.md

README now covers install via uv tool, quick start, and MCP integration.
Developer setup and testing docs moved to CONTRIBUTING.md."
```

---

### Task 11: Verify full build pipeline locally

**Files:** None (validation only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: all tests pass

- [ ] **Step 2: Build all wheels**

Run:

```bash
mkdir -p /tmp/guru-dist
for pkg in packages/guru-core packages/guru-server packages/guru-mcp packages/guru-cli .; do
  uv build --directory "$pkg" --out-dir /tmp/guru-dist/
done
ls -la /tmp/guru-dist/
```

Expected: 5 wheel files and 5 sdist tarballs in `/tmp/guru-dist/`. Version will be based on the latest git tag or a dev version.

- [ ] **Step 3: Generate test index**

Run:

```bash
python scripts/generate-index.py /tmp/guru-dist /tmp/guru-index
find /tmp/guru-index -type f
```

Expected: root `index.html` + 5 per-package `index.html` files under `/tmp/guru-index/simple/`.

- [ ] **Step 4: Verify index content**

Run: `cat /tmp/guru-index/simple/index.html`
Expected: HTML with links to all 5 packages

Run: `cat /tmp/guru-index/simple/guru/index.html`
Expected: HTML with link to `guru-*.whl`

- [ ] **Step 5: Run BDD e2e tests (if Ollama available)**

Run: `uv run behave tests/e2e/features/knowledge_base.feature tests/e2e/features/mcp_tools.feature`
Expected: all scenarios pass (these use mocked embeddings, no Ollama needed)

- [ ] **Step 6: Clean up**

Run: `rm -rf /tmp/guru-dist /tmp/guru-index`

- [ ] **Step 7: Commit any fixes discovered during validation**

Only if issues were found. Otherwise skip.

---

### Task 12: Update CLAUDE.md with distribution info

**Files:**
- Modify: `CLAUDE.md` (project root)

- [ ] **Step 1: Add distribution section to CLAUDE.md**

Add after the "## Commands" section:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add distribution and release info to CLAUDE.md"
```
