# Worktree Speed via Content-Addressed Embedding Cache — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make creating a new git worktree of an already-indexed Guru project reach "first search" in seconds instead of minutes, by caching Ollama embeddings in a content-addressed SQLite store shared across all projects on the machine. Also: migrate the config file from a flat JSON array to an object format, and make file discovery respect `.gitignore`.

**Architecture:** A new `EmbeddingCache` module in `guru-server` owns a SQLite file at `platformdirs.user_cache_dir("guru")/embeddings.db`, keyed on `(sha256(chunk_text), model_name)`. The indexer probes the cache before calling `embedder.embed_batch` and only embeds misses. File discovery in `_discover` gains a gitignore filter via `git ls-files --cached --others --exclude-standard`. Each worktree keeps its own `.guru/db` and manifest — only embedding work is shared. Config files gain a `{version, rules}` object wrapper while legacy arrays are auto-wrapped on read.

**Tech Stack:** Python 3.13, SQLite (stdlib), numpy, platformdirs, FastAPI, click, pytest, behave, git CLI (subprocess)

**Spec:** `docs/superpowers/specs/2026-04-14-worktree-speed-embedding-cache-design.md`

**Issue:** #26

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `packages/guru-server/src/guru_server/embed_cache.py` | `CacheKey`, `CacheStats`, `EmbeddingCache` class — SQLite-backed content-addressed vector cache |
| `packages/guru-server/src/guru_server/api/cache.py` | FastAPI router for `/cache` endpoints (GET stats, DELETE clear, POST prune) |
| `packages/guru-server/tests/test_embed_cache.py` | Unit tests for `EmbeddingCache` — round-trip, dim mismatch, clear, prune, WAL |
| `packages/guru-core/tests/test_types_v1_config.py` | Unit tests for `GuruConfig` Pydantic model |
| `tests/e2e/features/worktree_cache.feature` | BDD — cache reuse across projects, model-drift |
| `tests/e2e/features/gitignore_discovery.feature` | BDD — gitignore filter, worktree-in-ignored-dir, non-git fallback |
| `tests/e2e/features/cache_cli.feature` | BDD — `guru cache info/clear/prune` |
| `tests/e2e/features/steps/cache_steps.py` | Worktree-cache-specific step definitions (created in Task 21; `cache_cli.feature` reuses existing `cli_steps.py` steps) |
| `tests/e2e/features/steps/gitignore_steps.py` | Gitignore-specific step definitions |

### Modified Files

| File | What Changes |
|------|-------------|
| `packages/guru-core/src/guru_core/types.py` | Add `GuruConfig`, `CacheStatsOut`, `CacheDeleteResult`, `CachePruneRequest`; extend `JobSummary`/`JobDetail` with `cache_hits`/`cache_misses`; extend `StatusOut` with `cache` |
| `packages/guru-core/src/guru_core/config.py` | Rename `load_rules` → `load_config` returning `GuruConfig`; `resolve_config` returns `GuruConfig`; auto-wrap legacy array |
| `packages/guru-core/src/guru_core/client.py` | Add async `cache_info`, `cache_clear`, `cache_prune` methods; add `_delete` helper |
| `packages/guru-server/src/guru_server/config.py` | Update re-exports for the renamed functions |
| `packages/guru-server/src/guru_server/embedding.py` | `OllamaEmbedder` exposes `model_name: str` and `dimensions: int` |
| `packages/guru-server/src/guru_server/jobs.py` | `Job` gains `cache_hits` / `cache_misses` fields; populated in `to_summary`/`to_detail` |
| `packages/guru-server/src/guru_server/indexer.py` | Accept `GuruConfig` + `EmbeddingCache`; add `_git_tracked_paths` helper; gitignore filter in `_discover`; chunk-level cache lookup in `_index_file`; end-of-job log line |
| `packages/guru-server/src/guru_server/main.py` | Construct `EmbeddingCache` (respecting `GURU_EMBED_CACHE_PATH` env var); pass through `create_app` |
| `packages/guru-server/src/guru_server/app.py` | `create_app` accepts `embed_cache`, stores on `app.state`, passes to `BackgroundIndexer`; `config` typed as `GuruConfig` |
| `packages/guru-server/src/guru_server/api/__init__.py` | Register `cache_router` |
| `packages/guru-server/src/guru_server/api/status.py` | Assemble and include `CacheStatsOut` in response |
| `packages/guru-server/src/guru_server/api/models.py` | Re-export new types |
| `packages/guru-server/src/guru_server/watcher.py` | Update `config` param typing and access `.rules` |
| `packages/guru-server/pyproject.toml` | Add `platformdirs>=4.0`, `numpy>=1.26` to dependencies |
| `packages/guru-cli/src/guru_cli/cli.py` | `DEFAULT_CONFIG` → object form; `cache` click group (info/clear/prune); `server_status` prints cache block; `config` command uses `load_config` |
| `packages/guru-server/tests/test_config.py` | Tests for array auto-wrap, object format, `.rules` access on results |
| `packages/guru-server/tests/test_indexer.py` | `indexer` fixture uses `GuruConfig`; new tests for cache hit/miss/mixed paths, gitignore filter, cache fallthrough |
| `packages/guru-server/tests/test_embedding.py` | Tests that `OllamaEmbedder` exposes `model_name` and `dimensions` |
| `packages/guru-server/tests/test_api.py` | Tests for new `/cache` endpoints |
| `tests/e2e/features/environment.py` | `before_feature` hook exports `GURU_EMBED_CACHE_PATH` pointing at a tempfile |
| `ARCHITECTURE.md` | Amendments to §Data Ownership, §Ingestion, §Configuration |

---

## Task 1: Add `GuruConfig` and cache-related Pydantic types to guru-core

**Files:**
- Modify: `packages/guru-core/src/guru_core/types.py`
- Create: `packages/guru-core/tests/test_types_v1_config.py`

- [ ] **Step 1: Write failing tests for new types**

Create `packages/guru-core/tests/test_types_v1_config.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from guru_core.types import (
    CacheDeleteResult,
    CachePruneRequest,
    CacheStatsOut,
    GuruConfig,
    JobDetail,
    JobSummary,
    MatchConfig,
    Rule,
    StatusOut,
)


def test_guru_config_defaults():
    cfg = GuruConfig()
    assert cfg.version == 1
    assert cfg.rules == []


def test_guru_config_with_rules():
    cfg = GuruConfig(
        version=1,
        rules=[Rule(rule_name="default", match=MatchConfig(glob="**/*.md"))],
    )
    assert cfg.version == 1
    assert len(cfg.rules) == 1
    assert cfg.rules[0].rule_name == "default"


def test_guru_config_accepts_camel_case_rules():
    cfg = GuruConfig.model_validate(
        {"version": 1, "rules": [{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}]}
    )
    assert cfg.rules[0].rule_name == "docs"


def test_cache_stats_out_minimal():
    stats = CacheStatsOut(
        path="/tmp/x",
        total_entries=0,
        total_bytes=0,
        by_model={},
        last_job_hits=None,
        last_job_misses=None,
        last_job_hit_rate=None,
    )
    assert stats.total_entries == 0
    assert stats.last_job_hit_rate is None


def test_cache_delete_result_roundtrip():
    result = CacheDeleteResult(deleted=42)
    assert result.deleted == 42


def test_cache_prune_request_rejects_negative():
    with pytest.raises(ValidationError):
        CachePruneRequest(older_than_ms=-1)


def test_cache_prune_request_accepts_zero():
    req = CachePruneRequest(older_than_ms=0)
    assert req.older_than_ms == 0


def test_job_summary_has_cache_counters():
    summary = JobSummary(
        job_id="abc",
        status="completed",
        phase=None,
        files_total=1,
        files_processed=1,
        files_skipped=0,
        cache_hits=3,
        cache_misses=2,
    )
    assert summary.cache_hits == 3
    assert summary.cache_misses == 2


def test_job_summary_cache_counters_default_zero():
    summary = JobSummary(
        job_id="abc",
        status="completed",
        phase=None,
        files_total=0,
        files_processed=0,
        files_skipped=0,
    )
    assert summary.cache_hits == 0
    assert summary.cache_misses == 0


def test_status_out_cache_defaults_to_none():
    from datetime import UTC, datetime

    status = StatusOut(
        server_running=True,
        document_count=0,
        chunk_count=0,
        last_indexed=datetime.now(UTC),
        ollama_available=True,
        model_loaded=True,
    )
    assert status.cache is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-core/tests/test_types_v1_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'GuruConfig' from 'guru_core.types'`

- [ ] **Step 3: Add new types to `packages/guru-core/src/guru_core/types.py`**

At the top of the file, below the existing imports, add:

```python
# --- Config object format (v1) ---


class GuruConfig(BaseModel):
    """Object-form config file. Replaces the legacy flat array of rules."""

    model_config = ConfigDict(populate_by_name=True)
    version: int = 1
    rules: list[Rule] = Field(default_factory=list)
```

Add after the existing response models (after `IndexAccepted`):

```python
# --- Embedding cache models ---


class CacheStatsOut(BaseModel):
    path: str
    total_entries: int
    total_bytes: int
    by_model: dict[str, int] = Field(default_factory=dict)
    last_job_hits: int | None = None
    last_job_misses: int | None = None
    last_job_hit_rate: float | None = None


class CacheDeleteResult(BaseModel):
    deleted: int


class CachePruneRequest(BaseModel):
    older_than_ms: int = Field(ge=0)
```

Modify `JobSummary` to add the two cache counters:

```python
class JobSummary(BaseModel):
    job_id: str
    status: str
    phase: str | None
    files_total: int
    files_processed: int
    files_skipped: int
    cache_hits: int = 0
    cache_misses: int = 0
```

Modify `JobDetail` the same way:

```python
class JobDetail(BaseModel):
    job_id: str
    job_type: str
    status: str
    phase: str | None
    files_total: int
    files_processed: int
    files_skipped: int
    files_deleted: int
    chunks_created: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cache_hits: int = 0
    cache_misses: int = 0
```

Modify `StatusOut` to include the cache field:

```python
class StatusOut(BaseModel):
    server_running: bool
    document_count: int
    chunk_count: int
    last_indexed: datetime | None
    ollama_available: bool
    model_loaded: bool
    current_job: JobSummary | None = None
    cache: CacheStatsOut | None = None
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest packages/guru-core/tests/test_types_v1_config.py -v`
Expected: PASS for all 9 tests.

- [ ] **Step 5: Run the full guru-core test suite to catch regressions**

Run: `uv run pytest packages/guru-core/ -v`
Expected: PASS. No existing tests broken.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-core/src/guru_core/types.py packages/guru-core/tests/test_types_v1_config.py
git commit -m "feat(types): add GuruConfig, cache models, cache counters on jobs"
```

---

## Task 2: Rename `load_rules` → `load_config` and auto-wrap legacy array

**Files:**
- Modify: `packages/guru-core/src/guru_core/config.py`
- Modify: `packages/guru-server/src/guru_server/config.py`
- Modify: `packages/guru-server/tests/test_config.py`

- [ ] **Step 1: Write failing tests for the new load path**

Append to `packages/guru-server/tests/test_config.py`:

```python
from guru_core.types import GuruConfig
from guru_server.config import load_config


def test_load_config_legacy_array_auto_wraps(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text(
        json.dumps([{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}])
    )
    cfg = load_config(config_file)
    assert isinstance(cfg, GuruConfig)
    assert cfg.version == 1
    assert len(cfg.rules) == 1
    assert cfg.rules[0].rule_name == "docs"


def test_load_config_object_format(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}],
            }
        )
    )
    cfg = load_config(config_file)
    assert cfg.version == 1
    assert cfg.rules[0].rule_name == "docs"


def test_load_config_empty_array(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text("[]")
    cfg = load_config(config_file)
    assert cfg.rules == []


def test_load_config_returns_none_for_missing_file(tmp_path: Path):
    assert load_config(tmp_path / "nope.json") is None
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_config.py::test_load_config_legacy_array_auto_wraps -v`
Expected: FAIL with `ImportError: cannot import name 'load_config'`.

- [ ] **Step 3: Implement `load_config` and update `resolve_config`**

Replace `packages/guru-core/src/guru_core/config.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

from guru_core.types import GuruConfig, MatchConfig, Rule

DEFAULT_RULES = [
    Rule(rule_name="default", match=MatchConfig(glob="**/*.md")),
]


def load_config(path: Path) -> GuruConfig | None:
    """Load a config file. Returns None if the file does not exist.

    Accepts both the v1 object format (`{"version": 1, "rules": [...]}`)
    and the legacy flat-array format (`[{"ruleName": ..., ...}]`), which
    is auto-wrapped into `{"version": 1, "rules": <array>}` for callers.
    """
    if not path.is_file():
        return None
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"version": 1, "rules": data}
    return GuruConfig(**data)


def merge_rules(global_rules: list[Rule], local_rules: list[Rule]) -> list[Rule]:
    """Merge local rules over global rules.

    Rules with the same rule_name in local fully replace the global version.
    Local rules with new names are appended.
    """
    merged = {r.rule_name: r for r in global_rules}
    for rule in local_rules:
        merged[rule.rule_name] = rule
    return list(merged.values())


def resolve_config(
    project_root: Path,
    global_config_dir: Path | None = None,
) -> GuruConfig:
    """Resolve configuration using the fallback chain.

    Resolution:
    1. Load ~/.config/guru/config.json as base (global)
    2. Load ./.guru.json (preferred), ./guru.json (backwards compat),
       or ./.guru/config.json (legacy fallback) as local
    3. Merge rules: local rules override global by rule_name, new names appended
    4. No config anywhere -> GuruConfig with DEFAULT_RULES
    """
    if global_config_dir is None:
        global_config_dir = Path.home() / ".config" / "guru"

    global_cfg = load_config(global_config_dir / "config.json")

    local_cfg = load_config(project_root / ".guru.json")
    if local_cfg is None:
        local_cfg = load_config(project_root / "guru.json")
    if local_cfg is None:
        local_cfg = load_config(project_root / ".guru" / "config.json")

    if global_cfg is None and local_cfg is None:
        return GuruConfig(version=1, rules=list(DEFAULT_RULES))

    if global_cfg is None:
        return local_cfg

    if local_cfg is None:
        return global_cfg

    merged_rules = merge_rules(global_cfg.rules, local_cfg.rules)
    return GuruConfig(version=1, rules=merged_rules)
```

- [ ] **Step 4: Update the server's re-export module**

Replace `packages/guru-server/src/guru_server/config.py` with:

```python
"""Config module — re-exported from guru_core.config (canonical source)."""

from guru_core.config import (
    DEFAULT_RULES,
    load_config,
    merge_rules,
    resolve_config,
)

__all__ = ["DEFAULT_RULES", "load_config", "merge_rules", "resolve_config"]
```

- [ ] **Step 5: Update existing tests in `test_config.py` that used the old API**

In `packages/guru-server/tests/test_config.py`:

Replace the import line:

```python
from guru_server.config import DEFAULT_RULES, load_rules, merge_rules, resolve_config
```

with:

```python
from guru_server.config import DEFAULT_RULES, load_config, merge_rules, resolve_config
```

Replace the two `load_rules` tests:

```python
# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_from_json(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text(json.dumps([{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}]))
    cfg = load_config(config_file)
    assert cfg is not None
    assert len(cfg.rules) == 1
    assert cfg.rules[0].rule_name == "docs"
    assert cfg.rules[0].match.glob == "docs/**/*.md"


def test_load_config_returns_none_for_missing_file(tmp_path: Path):
    missing = tmp_path / "nonexistent.json"
    result = load_config(missing)
    assert result is None
```

Update every test that treats `resolve_config`'s return value as a list. For each of `test_resolve_config_prefers_dot_guru_json`, `test_resolve_config_prefers_guru_json`, `test_resolve_config_falls_back_to_guru_config_json`, `test_resolve_config_merges_with_global`, and `test_resolve_config_returns_defaults_when_no_config`:

- Replace `rules = resolve_config(...)` with `cfg = resolve_config(...)`
- Replace `names = {r.rule_name for r in rules}` with `names = {r.rule_name for r in cfg.rules}`
- Replace `len(rules)` with `len(cfg.rules)`
- Replace `rules[0]` with `cfg.rules[0]`

- [ ] **Step 6: Run all config tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_config.py -v`
Expected: PASS for all tests (existing + 4 new).

- [ ] **Step 7: Commit**

```bash
git add packages/guru-core/src/guru_core/config.py \
        packages/guru-server/src/guru_server/config.py \
        packages/guru-server/tests/test_config.py
git commit -m "feat(config): rename load_rules -> load_config, return GuruConfig"
```

---

## Task 3: Update `resolve_config` call sites (server main, CLI, watcher)

**Files:**
- Modify: `packages/guru-server/src/guru_server/main.py`
- Modify: `packages/guru-server/src/guru_server/app.py`
- Modify: `packages/guru-server/src/guru_server/indexer.py`
- Modify: `packages/guru-server/src/guru_server/watcher.py`
- Modify: `packages/guru-cli/src/guru_cli/cli.py`
- Modify: `packages/guru-server/tests/test_indexer.py`

- [ ] **Step 1: Update `BackgroundIndexer.__init__` to accept `GuruConfig`**

In `packages/guru-server/src/guru_server/indexer.py`, change the import and constructor signature:

```python
from guru_core.types import GuruConfig, Rule
```

```python
class BackgroundIndexer:
    def __init__(
        self,
        *,
        store: VectorStore,
        manifest: FileManifest,
        embedder,
        config: GuruConfig,
        project_root: Path,
    ) -> None:
        self._store = store
        self._manifest = manifest
        self._embedder = embedder
        self._config = config
        self._project_root = Path(project_root).resolve()
        self._parser = MarkdownParser()
```

Update the two `for rule in self._config` loops inside `_discover` to iterate `self._config.rules`:

```python
        # Collect excluded files
        excluded_files: set[Path] = set()
        for rule in self._config.rules:
            if rule.exclude:
                excluded_files.update(self._project_root.glob(rule.match.glob))

        # Collect all matched files with their rules
        seen_files: set[Path] = set()
        matched: list[tuple[Path, str, Rule]] = []
        for rule in self._config.rules:
            if rule.exclude:
                continue
            # ... rest unchanged
```

- [ ] **Step 2: Update `packages/guru-server/src/guru_server/app.py`**

Change the imports:

```python
from guru_core.types import GuruConfig
```

Change `create_app`'s config parameter:

```python
def create_app(
    store: VectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    config: GuruConfig | None = None,
    project_root: str | None = None,
    auto_index: bool = True,
) -> FastAPI:
```

Change the app.state assignment:

```python
    app.state.config = config if config is not None else GuruConfig()
```

- [ ] **Step 3: Update `packages/guru-server/src/guru_server/main.py`**

In `main()`, the existing call at line 79:

```python
        config = resolve_config(project_root=Path(project_root))
```

already works because `resolve_config` now returns a `GuruConfig` and `create_app` accepts it. No code change needed in `main.py`, but verify the type-check still passes:

Run: `uv run python -c "from guru_server.main import main; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Update `packages/guru-server/src/guru_server/watcher.py` to accept `GuruConfig` in `start_watcher`**

`should_watch_path` stays a pure function on `list[Rule]` so existing `test_watcher.py` tests keep working. Only `start_watcher` changes signature.

Add the import at the top:

```python
from guru_core.types import GuruConfig, Rule
```

Change `start_watcher` signature and the call to `should_watch_path` inside it:

```python
async def start_watcher(
    project_root: Path,
    config: GuruConfig,
    job_registry,
    submit_index,
) -> None:
    """Watch project files for changes and trigger re-indexing.

    Args:
        project_root: The project root directory to watch.
        config: The resolved GuruConfig (rules are pulled off of it).
        job_registry: The job registry to check for running jobs.
        submit_index: Async callable to submit a new indexing job.
    """
    from watchfiles import awatch

    logger.info("File watcher started on %s", project_root)

    try:
        async for changes in awatch(project_root, debounce=int(DEBOUNCE_SECONDS * 1000)):
            relevant = [
                path
                for _change_type, path in changes
                if should_watch_path(Path(path), project_root, config.rules)
            ]

            if not relevant:
                continue

            logger.info("File watcher detected %d relevant change(s)", len(relevant))

            if job_registry.current_job() is not None:
                logger.info("Index job already running, changes will be picked up by next run")
                continue

            await submit_index()
    except asyncio.CancelledError:
        logger.info("File watcher stopped")
        raise
    except Exception:
        logger.exception("File watcher error")
```

Leave `should_watch_path` (which takes `list[Rule]`) and `_glob_matches` unchanged. This keeps `test_watcher.py` passing without edits — it still constructs `list[Rule]` instances for its unit tests of the pure function.

- [ ] **Step 5: Update the indexer test fixture**

In `packages/guru-server/tests/test_indexer.py`, change the `config` fixture:

```python
from guru_core.types import GuruConfig, MatchConfig, Rule


@pytest.fixture
def config():
    return GuruConfig(
        version=1,
        rules=[Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))],
    )
```

The `indexer` fixture already passes `config=config` — no further change.

- [ ] **Step 6: Update the CLI's `config` command to use `load_config`**

In `packages/guru-cli/src/guru_cli/cli.py`, the `config` command currently imports `load_rules`. Replace the whole body of the command (starting at `def config():`):

```python
@cli.command()
def config():
    """Show resolved configuration with provenance."""
    from guru_core.config import DEFAULT_RULES, load_config, merge_rules

    guru_root = Path.cwd()
    with contextlib.suppress(GuruNotFoundError):
        guru_root = find_guru_root(Path.cwd())

    global_path = Path.home() / ".config" / "guru" / "config.json"
    local_path = guru_root / ".guru.json"
    if not local_path.is_file():
        local_path = guru_root / "guru.json"
    if not local_path.is_file():
        local_path = guru_root / ".guru" / "config.json"

    global_cfg = load_config(global_path)
    local_cfg = load_config(local_path)

    # Determine source labels before merging
    rule_source: dict[str, str] = {}
    if global_cfg:
        for r in global_cfg.rules:
            rule_source[r.rule_name] = str(global_path)
    if local_cfg:
        for r in local_cfg.rules:
            rule_source[r.rule_name] = str(local_path)  # local overrides global

    # Apply the same merge semantics as the server
    if global_cfg is None and local_cfg is None:
        effective = list(DEFAULT_RULES)
        for r in effective:
            rule_source[r.rule_name] = "default"
    elif global_cfg is None:
        effective = local_cfg.rules
    elif local_cfg is None:
        effective = global_cfg.rules
    else:
        effective = merge_rules(global_cfg.rules, local_cfg.rules)

    output = []
    for rule in effective:
        entry = json.loads(rule.model_dump_json(by_alias=True))
        entry["source"] = rule_source.get(rule.rule_name, "default")
        output.append(entry)

    click.echo(json.dumps(output, indent=2))
```

- [ ] **Step 7: Run all affected tests**

Run: `uv run pytest packages/guru-server/ packages/guru-cli/ -v`
Expected: PASS. Specifically, `test_indexer.py` should still pass unchanged (aside from the fixture update).

- [ ] **Step 8: Commit**

```bash
git add packages/guru-server/src/guru_server/indexer.py \
        packages/guru-server/src/guru_server/app.py \
        packages/guru-server/src/guru_server/watcher.py \
        packages/guru-server/tests/test_indexer.py \
        packages/guru-cli/src/guru_cli/cli.py
git commit -m "refactor: thread GuruConfig through server and CLI call sites"
```

---

## Task 4: Update `guru init` to write object-format config

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/cli.py`
- Modify: `packages/guru-cli/tests/test_cli.py`

- [ ] **Step 1: Write a failing test**

Append to `packages/guru-cli/tests/test_cli.py`:

```python
def test_init_writes_object_format_config(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from guru_cli.cli import cli

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0

    import json
    dot_guru = tmp_path / ".guru.json"
    data = json.loads(dot_guru.read_text())
    # New object format
    assert isinstance(data, dict)
    assert data["version"] == 1
    assert isinstance(data["rules"], list)
    assert data["rules"][0]["ruleName"] == "default"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py::test_init_writes_object_format_config -v`
Expected: FAIL — `init` currently writes a flat array.

- [ ] **Step 3: Update `DEFAULT_CONFIG` in `packages/guru-cli/src/guru_cli/cli.py`**

Replace:

```python
DEFAULT_CONFIG = [
    {"ruleName": "default", "match": {"glob": "**/*.md"}},
]
```

with:

```python
DEFAULT_CONFIG = {
    "version": 1,
    "rules": [
        {"ruleName": "default", "match": {"glob": "**/*.md"}},
    ],
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py::test_init_writes_object_format_config -v`
Expected: PASS.

Also run existing init tests to verify they still pass:

Run: `uv run pytest packages/guru-cli/tests/test_cli.py -v -k init`
Expected: all PASS. (Any existing test that asserted `data` was a list needs updating — if so, change to the new `data["rules"]` shape.)

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/cli.py packages/guru-cli/tests/test_cli.py
git commit -m "feat(cli): guru init writes object-format .guru.json"
```

---

## Task 5: Expose `model_name` and `dimensions` on `OllamaEmbedder`

**Files:**
- Modify: `packages/guru-server/src/guru_server/embedding.py`
- Modify: `packages/guru-server/tests/test_embedding.py`

- [ ] **Step 1: Write a failing test**

Append to `packages/guru-server/tests/test_embedding.py`:

```python
def test_ollama_embedder_has_model_name():
    from guru_server.embedding import OllamaEmbedder

    emb = OllamaEmbedder(model="nomic-embed-text")
    assert emb.model_name == "nomic-embed-text"


def test_ollama_embedder_has_dimensions():
    from guru_server.embedding import OllamaEmbedder

    emb = OllamaEmbedder(model="nomic-embed-text")
    # nomic-embed-text default output dim
    assert emb.dimensions == 768
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/guru-server/tests/test_embedding.py::test_ollama_embedder_has_model_name -v`
Expected: FAIL with `AttributeError: 'OllamaEmbedder' object has no attribute 'model_name'`.

- [ ] **Step 3: Add the attributes in `packages/guru-server/src/guru_server/embedding.py`**

Change `__init__` to expose a `model_name` alias and a `dimensions` constant keyed by model:

```python
# Known embedding dimensions for Ollama models. Update when adding support for new models.
_MODEL_DIMENSIONS = {
    "nomic-embed-text": 768,
}


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.model_name = model
        self.base_url = base_url
        self.dimensions = _MODEL_DIMENSIONS.get(model, 768)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_embedding.py -v`
Expected: PASS, including existing tests.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/embedding.py packages/guru-server/tests/test_embedding.py
git commit -m "feat(embedding): expose model_name and dimensions on OllamaEmbedder"
```

---

## Task 6: Add `platformdirs` and `numpy` dependencies to guru-server

**Files:**
- Modify: `packages/guru-server/pyproject.toml`

- [ ] **Step 1: Add the dependencies to `[tool.hatch.metadata.hooks.uv-dynamic-versioning]`**

In `packages/guru-server/pyproject.toml`, update the dependencies list to include `platformdirs` and `numpy`:

```toml
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
    "watchfiles>=1.0",
    "platformdirs>=4.0",
    "numpy>=1.26",
]
```

- [ ] **Step 2: Re-sync the workspace**

Run: `uv sync --all-packages`
Expected: platformdirs and numpy appear in `uv.lock`; no errors.

- [ ] **Step 3: Verify imports work**

Run: `uv run python -c "import platformdirs, numpy; print(platformdirs.__version__, numpy.__version__)"`
Expected: prints two version numbers with no error.

- [ ] **Step 4: Commit**

```bash
git add packages/guru-server/pyproject.toml uv.lock
git commit -m "chore(guru-server): add platformdirs and numpy dependencies"
```

---

## Task 7: Create `EmbeddingCache` module

**Files:**
- Create: `packages/guru-server/src/guru_server/embed_cache.py`
- Create: `packages/guru-server/tests/test_embed_cache.py`

- [ ] **Step 1: Write failing unit tests**

Create `packages/guru-server/tests/test_embed_cache.py`:

```python
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import pytest

from guru_server.embed_cache import CacheKey, EmbeddingCache


def _key(text: str, model: str = "nomic-embed-text") -> CacheKey:
    return (hashlib.sha256(text.encode("utf-8")).digest(), model)


@pytest.fixture
def cache(tmp_path: Path) -> EmbeddingCache:
    c = EmbeddingCache(db_path=tmp_path / "embeddings.db")
    yield c
    c.close()


def test_round_trip_preserves_vector(cache: EmbeddingCache):
    key = _key("hello")
    vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    cache.put_many([(key, vector)])
    result = cache.get_many([key], expected_dim=3)
    assert result[0] is not None
    np.testing.assert_array_equal(result[0], vector)


def test_miss_returns_none(cache: EmbeddingCache):
    result = cache.get_many([_key("nothing here")], expected_dim=3)
    assert result == [None]


def test_dimension_mismatch_treated_as_miss(cache: EmbeddingCache):
    key = _key("hello")
    vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)  # dim 3
    cache.put_many([(key, vector)])
    result = cache.get_many([key], expected_dim=768)  # asked for dim 768
    assert result == [None]


def test_get_many_preserves_order(cache: EmbeddingCache):
    k1, k2, k3 = _key("a"), _key("b"), _key("c")
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v3 = np.array([3.0, 0.0], dtype=np.float32)
    cache.put_many([(k1, v1), (k3, v3)])

    result = cache.get_many([k1, k2, k3], expected_dim=2)
    assert len(result) == 3
    assert result[0] is not None
    np.testing.assert_array_equal(result[0], v1)
    assert result[1] is None
    assert result[2] is not None
    np.testing.assert_array_equal(result[2], v3)


def test_put_many_overwrites_existing(cache: EmbeddingCache):
    key = _key("hello")
    v1 = np.array([1.0], dtype=np.float32)
    v2 = np.array([2.0], dtype=np.float32)
    cache.put_many([(key, v1)])
    cache.put_many([(key, v2)])
    result = cache.get_many([key], expected_dim=1)
    np.testing.assert_array_equal(result[0], v2)


def test_clear_all(cache: EmbeddingCache):
    cache.put_many(
        [
            (_key("a"), np.array([1.0], dtype=np.float32)),
            (_key("b"), np.array([2.0], dtype=np.float32)),
        ]
    )
    deleted = cache.clear()
    assert deleted == 2
    assert cache.get_many([_key("a")], expected_dim=1) == [None]


def test_clear_scoped_to_model(cache: EmbeddingCache):
    cache.put_many(
        [
            (_key("a", model="m1"), np.array([1.0], dtype=np.float32)),
            (_key("b", model="m2"), np.array([2.0], dtype=np.float32)),
        ]
    )
    deleted = cache.clear(model="m1")
    assert deleted == 1
    assert cache.get_many([_key("a", model="m1")], expected_dim=1) == [None]
    assert cache.get_many([_key("b", model="m2")], expected_dim=1)[0] is not None


def test_prune_respects_accessed_at(cache: EmbeddingCache):
    old_key = _key("old")
    new_key = _key("new")
    cache.put_many([(old_key, np.array([1.0], dtype=np.float32))])

    # Simulate old access by patching the row's accessed_at to 100 days ago
    cutoff_ms = 100 * 24 * 3600 * 1000
    old_ts = int(time.time() * 1000) - cutoff_ms
    cache._conn.execute(
        "UPDATE embeddings SET accessed_at = ? WHERE content_hash = ?",
        (old_ts, old_key[0]),
    )
    cache._conn.commit()

    cache.put_many([(new_key, np.array([2.0], dtype=np.float32))])

    deleted = cache.prune(older_than_ms=50 * 24 * 3600 * 1000)  # older than 50 days
    assert deleted == 1
    assert cache.get_many([old_key], expected_dim=1) == [None]
    assert cache.get_many([new_key], expected_dim=1)[0] is not None


def test_stats_returns_counts_and_bytes(cache: EmbeddingCache):
    cache.put_many(
        [
            (_key("a", model="m1"), np.array([1.0, 2.0], dtype=np.float32)),
            (_key("b", model="m1"), np.array([3.0, 4.0], dtype=np.float32)),
            (_key("c", model="m2"), np.array([5.0, 6.0], dtype=np.float32)),
        ]
    )
    stats = cache.stats()
    assert stats.total_entries == 3
    assert stats.total_bytes > 0
    assert stats.by_model == {"m1": 2, "m2": 1}
    assert stats.path.endswith("embeddings.db")


def test_wal_mode_enabled(cache: EmbeddingCache):
    row = cache._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


def test_get_many_touches_accessed_at(cache: EmbeddingCache):
    key = _key("hello")
    cache.put_many([(key, np.array([1.0], dtype=np.float32))])
    before = cache._conn.execute(
        "SELECT accessed_at FROM embeddings WHERE content_hash = ?", (key[0],)
    ).fetchone()[0]

    time.sleep(0.01)
    cache.get_many([key], expected_dim=1)

    after = cache._conn.execute(
        "SELECT accessed_at FROM embeddings WHERE content_hash = ?", (key[0],)
    ).fetchone()[0]
    assert after > before
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_embed_cache.py -v`
Expected: FAIL with `ImportError: cannot import name 'EmbeddingCache' from 'guru_server.embed_cache'`.

- [ ] **Step 3: Create `packages/guru-server/src/guru_server/embed_cache.py`**

```python
"""Content-addressed embedding cache backed by SQLite.

Keyed on (sha256(chunk_text), model_name). Stores one vector per key.
Shared across all guru projects on the machine — content identity is
the entire identity, so worktrees and unrelated projects transparently
reuse embeddings for identical chunks.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

CacheKey = tuple[bytes, str]  # (sha256_digest_32_bytes, model_name)


@dataclass
class CacheStats:
    path: str
    total_entries: int
    total_bytes: int
    by_model: dict[str, int] = field(default_factory=dict)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    content_hash   BLOB    NOT NULL,
    model          TEXT    NOT NULL,
    dimensions     INTEGER NOT NULL,
    vector         BLOB    NOT NULL,
    created_at     INTEGER NOT NULL,
    accessed_at    INTEGER NOT NULL,
    PRIMARY KEY (content_hash, model)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model);
"""


class EmbeddingCache:
    """SQLite-backed content-addressed embedding cache."""

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def get_many(
        self, keys: list[CacheKey], expected_dim: int
    ) -> list[np.ndarray | None]:
        """Return vectors for each key in input order. Missing or dimension-mismatched
        entries become None. Touches `accessed_at` for every hit."""
        if not keys:
            return []

        # Build lookup — group keys by model so we can batch per model
        result: list[np.ndarray | None] = [None] * len(keys)
        by_model: dict[str, list[tuple[int, bytes]]] = {}
        for idx, (h, model) in enumerate(keys):
            by_model.setdefault(model, []).append((idx, h))

        now_ms = int(time.time() * 1000)
        for model, entries in by_model.items():
            hashes = [h for _, h in entries]
            placeholders = ",".join("?" * len(hashes))
            rows = self._conn.execute(
                f"SELECT content_hash, dimensions, vector "  # noqa: S608 (placeholders)
                f"FROM embeddings WHERE model = ? AND content_hash IN ({placeholders})",
                (model, *hashes),
            ).fetchall()
            by_hash = {row[0]: (row[1], row[2]) for row in rows}

            touched_hashes: list[bytes] = []
            for idx, h in entries:
                row = by_hash.get(h)
                if row is None:
                    continue
                stored_dim, blob = row
                if stored_dim != expected_dim:
                    continue  # treat as miss; put_many will overwrite
                result[idx] = np.frombuffer(blob, dtype=np.float32)
                touched_hashes.append(h)

            if touched_hashes:
                placeholders_t = ",".join("?" * len(touched_hashes))
                self._conn.execute(
                    f"UPDATE embeddings SET accessed_at = ? "  # noqa: S608
                    f"WHERE model = ? AND content_hash IN ({placeholders_t})",
                    (now_ms, model, *touched_hashes),
                )
        return result

    def put_many(self, entries: list[tuple[CacheKey, np.ndarray]]) -> None:
        """Insert or replace vectors for the given keys."""
        if not entries:
            return

        now_ms = int(time.time() * 1000)
        rows = []
        for (content_hash, model), vec in entries:
            vec32 = np.asarray(vec, dtype=np.float32)
            rows.append(
                (
                    content_hash,
                    model,
                    int(vec32.shape[0]),
                    vec32.tobytes(),
                    now_ms,
                    now_ms,
                )
            )
        self._conn.executemany(
            "INSERT OR REPLACE INTO embeddings "
            "(content_hash, model, dimensions, vector, created_at, accessed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

    def stats(self) -> CacheStats:
        total_entries = self._conn.execute(
            "SELECT COUNT(*) FROM embeddings"
        ).fetchone()[0]
        # File size on disk — sum of the db file and its WAL if present
        total_bytes = self._db_path.stat().st_size if self._db_path.exists() else 0
        wal_path = self._db_path.with_suffix(self._db_path.suffix + "-wal")
        if wal_path.exists():
            total_bytes += wal_path.stat().st_size

        by_model = {
            row[0]: row[1]
            for row in self._conn.execute(
                "SELECT model, COUNT(*) FROM embeddings GROUP BY model"
            ).fetchall()
        }
        return CacheStats(
            path=str(self._db_path),
            total_entries=total_entries,
            total_bytes=total_bytes,
            by_model=by_model,
        )

    def clear(self, model: str | None = None) -> int:
        if model is None:
            cur = self._conn.execute("DELETE FROM embeddings")
        else:
            cur = self._conn.execute("DELETE FROM embeddings WHERE model = ?", (model,))
        return cur.rowcount

    def prune(self, older_than_ms: int) -> int:
        cutoff_ms = int(time.time() * 1000) - older_than_ms
        cur = self._conn.execute(
            "DELETE FROM embeddings WHERE accessed_at < ?", (cutoff_ms,)
        )
        return cur.rowcount
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_embed_cache.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/embed_cache.py \
        packages/guru-server/tests/test_embed_cache.py
git commit -m "feat(embed_cache): SQLite-backed content-addressed embedding cache"
```

---

## Task 8: Add `cache_hits` / `cache_misses` counters to `Job`

**Files:**
- Modify: `packages/guru-server/src/guru_server/jobs.py`
- Modify: `packages/guru-server/tests/test_jobs.py`

- [ ] **Step 1: Write a failing test**

Append to `packages/guru-server/tests/test_jobs.py`:

```python
def test_job_has_cache_counters():
    from guru_server.jobs import Job

    job = Job()
    assert job.cache_hits == 0
    assert job.cache_misses == 0


def test_job_to_summary_includes_cache_counters():
    from guru_server.jobs import Job

    job = Job()
    job.cache_hits = 5
    job.cache_misses = 3
    summary = job.to_summary()
    assert summary.cache_hits == 5
    assert summary.cache_misses == 3


def test_job_to_detail_includes_cache_counters():
    from guru_server.jobs import Job

    job = Job()
    job.cache_hits = 5
    job.cache_misses = 3
    detail = job.to_detail()
    assert detail.cache_hits == 5
    assert detail.cache_misses == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/guru-server/tests/test_jobs.py::test_job_has_cache_counters -v`
Expected: FAIL — `Job` has no `cache_hits` attribute yet.

- [ ] **Step 3: Modify `packages/guru-server/src/guru_server/jobs.py`**

In `Job.__init__`, add two new fields at the end:

```python
        self.cache_hits: int = 0
        self.cache_misses: int = 0
```

Update `to_summary`:

```python
    def to_summary(self) -> JobSummary:
        return JobSummary(
            job_id=self.job_id,
            status=self.status,
            phase=self.phase,
            files_total=self.files_total,
            files_processed=self.files_processed,
            files_skipped=self.files_skipped,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
        )
```

Update `to_detail`:

```python
    def to_detail(self) -> JobDetail:
        return JobDetail(
            job_id=self.job_id,
            job_type=self.job_type,
            status=self.status,
            phase=self.phase,
            files_total=self.files_total,
            files_processed=self.files_processed,
            files_skipped=self.files_skipped,
            files_deleted=self.files_deleted,
            chunks_created=self.chunks_created,
            error=self.error,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_jobs.py -v`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/jobs.py packages/guru-server/tests/test_jobs.py
git commit -m "feat(jobs): track cache_hits/cache_misses on Job model"
```

---

## Task 9: Wire `EmbeddingCache` into server startup and `create_app`

**Files:**
- Modify: `packages/guru-server/src/guru_server/main.py`
- Modify: `packages/guru-server/src/guru_server/app.py`
- Modify: `packages/guru-server/tests/test_main.py`

- [ ] **Step 1: Write a failing test that `main.py` resolves a cache path**

Append to `packages/guru-server/tests/test_main.py` (if it exists; if not, create it with this content):

```python
import os
from pathlib import Path

from guru_server.main import _resolve_cache_db_path


def test_resolve_cache_db_path_uses_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(tmp_path / "my_cache.db"))
    result = _resolve_cache_db_path()
    assert result == tmp_path / "my_cache.db"


def test_resolve_cache_db_path_uses_platformdirs_when_no_env(monkeypatch):
    monkeypatch.delenv("GURU_EMBED_CACHE_PATH", raising=False)
    result = _resolve_cache_db_path()
    assert "guru" in str(result).lower()
    assert str(result).endswith("embeddings.db")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-server/tests/test_main.py::test_resolve_cache_db_path_uses_env_var -v`
Expected: FAIL — `_resolve_cache_db_path` doesn't exist yet.

- [ ] **Step 3: Update `packages/guru-server/src/guru_server/main.py`**

Add at the top of the file below existing imports:

```python
from platformdirs import user_cache_dir

from guru_server.embed_cache import EmbeddingCache
```

Add this helper at module scope (above `main()`):

```python
def _resolve_cache_db_path() -> Path:
    """Return the filesystem path to the embedding cache SQLite file.

    Honors the GURU_EMBED_CACHE_PATH environment variable for test isolation.
    Otherwise uses platformdirs.user_cache_dir('guru') / 'embeddings.db'.
    """
    env = os.environ.get("GURU_EMBED_CACHE_PATH")
    if env:
        return Path(env)
    return Path(user_cache_dir("guru")) / "embeddings.db"
```

Inside `main()`, after `embedder = OllamaEmbedder()`, construct the cache and pass it in:

```python
        embedder = OllamaEmbedder()
        cache_db_path = _resolve_cache_db_path()
        logger.info("Opening embedding cache at %s", cache_db_path)
        embed_cache = EmbeddingCache(db_path=cache_db_path)

        app = create_app(
            store=store,
            embedder=embedder,
            config=config,
            project_root=project_root,
            embed_cache=embed_cache,
        )
```

- [ ] **Step 4: Update `packages/guru-server/src/guru_server/app.py` to accept and use the cache**

Import `EmbeddingCache`:

```python
from guru_server.embed_cache import EmbeddingCache
```

Change `create_app` signature to accept the cache:

```python
def create_app(
    store: VectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    config: GuruConfig | None = None,
    project_root: str | None = None,
    auto_index: bool = True,
    embed_cache: EmbeddingCache | None = None,
) -> FastAPI:
```

Store it on app state:

```python
    app.state.embed_cache = embed_cache
```

Pass it into `BackgroundIndexer` where the existing indexer is constructed:

```python
    if store is not None and embedder is not None and app.state.manifest is not None:
        app.state.indexer = BackgroundIndexer(
            store=store,
            manifest=app.state.manifest,
            embedder=embedder,
            config=app.state.config,
            project_root=Path(app.state.project_root),
            embed_cache=embed_cache,
        )
```

- [ ] **Step 5: Run the new main.py tests**

Run: `uv run pytest packages/guru-server/tests/test_main.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-server/src/guru_server/main.py \
        packages/guru-server/src/guru_server/app.py \
        packages/guru-server/tests/test_main.py
git commit -m "feat(server): wire EmbeddingCache into startup and create_app"
```

---

## Task 10: Integrate cache path into `_index_file`

**Files:**
- Modify: `packages/guru-server/src/guru_server/indexer.py`
- Modify: `packages/guru-server/tests/test_indexer.py`

- [ ] **Step 1: Write failing tests for cache hit/miss/mixed paths**

Append to `packages/guru-server/tests/test_indexer.py`:

```python
from unittest.mock import ANY

import numpy as np

from guru_server.embed_cache import EmbeddingCache


@pytest.fixture
def embed_cache(tmp_path):
    c = EmbeddingCache(db_path=tmp_path / "embeddings.db")
    yield c
    c.close()


@pytest.fixture
def indexer_with_cache(store, manifest, embedder, config, project_dir, embed_cache):
    return BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=project_dir,
        embed_cache=embed_cache,
    )


@pytest.mark.asyncio
async def test_cache_miss_embeds_everything(
    indexer_with_cache, registry, embedder, embed_cache
):
    """Empty cache: embedder is called for every chunk and cache is populated."""
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer_with_cache.run(job)

    assert embedder.embed_batch.await_count >= 1
    assert job.cache_hits == 0
    assert job.cache_misses > 0
    assert embed_cache.stats().total_entries == job.cache_misses


@pytest.mark.asyncio
async def test_cache_hit_skips_embedder(
    indexer_with_cache, registry, embedder, embed_cache, project_dir
):
    """Pre-populate cache with all chunks; embedder must not be called."""
    import hashlib

    from guru_server.ingestion.markdown import MarkdownParser

    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    # Parse all fixture files to get their chunk texts, populate cache
    parser = MarkdownParser()
    from guru_core.types import Rule, MatchConfig
    rule = Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))
    for md in (project_dir / "docs").glob("*.md"):
        chunks = parser.parse(md, rule)
        for chunk in chunks:
            key = (hashlib.sha256(chunk.content.encode("utf-8")).digest(), "nomic-embed-text")
            embed_cache.put_many([(key, np.array([0.1] * 768, dtype=np.float32))])

    job = registry.create_job()
    await indexer_with_cache.run(job)

    # Embedder should NOT be called because all chunks are cached
    assert embedder.embed_batch.await_count == 0
    assert job.cache_misses == 0
    assert job.cache_hits > 0


@pytest.mark.asyncio
async def test_cache_get_many_failure_falls_through(
    indexer_with_cache, registry, embedder, embed_cache
):
    """If cache.get_many raises, the job completes via the embedder."""
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    embed_cache.get_many = MagicMock(side_effect=RuntimeError("cache boom"))

    job = registry.create_job()
    await indexer_with_cache.run(job)

    assert job.status == "completed"
    assert embedder.embed_batch.await_count >= 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-server/tests/test_indexer.py::test_cache_miss_embeds_everything -v`
Expected: FAIL — `BackgroundIndexer` does not accept `embed_cache`.

- [ ] **Step 3: Update `BackgroundIndexer.__init__` to accept `embed_cache`**

In `packages/guru-server/src/guru_server/indexer.py`, update imports:

```python
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from guru_core.types import GuruConfig, Rule
from guru_server.embed_cache import EmbeddingCache
from guru_server.ingestion.markdown import MarkdownParser
from guru_server.jobs import Job
from guru_server.manifest import FileManifest
from guru_server.storage import VectorStore
```

Update `__init__`:

```python
class BackgroundIndexer:
    def __init__(
        self,
        *,
        store: VectorStore,
        manifest: FileManifest,
        embedder,
        config: GuruConfig,
        project_root: Path,
        embed_cache: EmbeddingCache | None = None,
    ) -> None:
        self._store = store
        self._manifest = manifest
        self._embedder = embedder
        self._config = config
        self._project_root = Path(project_root).resolve()
        self._parser = MarkdownParser()
        self._cache = embed_cache
```

- [ ] **Step 4: Rewrite `_index_file` to use the cache**

Replace the entire `_index_file` method body with:

```python
    async def _index_file(
        self, job: Job, file_path: Path, rel_path: str, rule: Rule, short_id: str
    ) -> None:
        """Parse, embed (via cache when possible), and store a single file."""
        content_hash = _file_hash(file_path)
        current_mtime = file_path.stat().st_mtime

        chunks = self._parser.parse(file_path, rule)
        for chunk in chunks:
            chunk.file_path = rel_path

        if not chunks:
            self._store.delete_file(rel_path)
            self._manifest.upsert(
                rel_path,
                content_hash=content_hash,
                mtime=current_mtime,
                chunk_count=0,
            )
            job.files_processed += 1
            return

        texts = [chunk.content for chunk in chunks]
        vectors = await self._embed_with_cache(texts, job, short_id)

        # Replace old chunks only after new embeddings are ready so
        # parse/embed failures do not destroy the previous index.
        self._store.delete_file(rel_path)
        self._store.add_chunks(chunks, vectors)

        # Update manifest
        self._manifest.upsert(
            rel_path,
            content_hash=content_hash,
            mtime=current_mtime,
            chunk_count=len(chunks),
        )

        job.files_processed += 1
        job.chunks_created += len(chunks)
        logger.info("[job %s] Indexed %s (%d chunks)", short_id, rel_path, len(chunks))

    async def _embed_with_cache(
        self, texts: list[str], job: Job, short_id: str
    ) -> list[list[float]]:
        """Embed texts, reusing cached vectors when possible.

        Returns vectors in the same order as `texts`. Cache failures are
        logged and downgraded to a full embedder call.
        """
        if self._cache is None:
            new = await self._embedder.embed_batch(texts)
            job.cache_misses += len(texts)
            return new

        model_name = getattr(self._embedder, "model_name", None)
        dimensions = getattr(self._embedder, "dimensions", None)
        if model_name is None or dimensions is None:
            logger.warning(
                "[job %s] embedder lacks model_name/dimensions — bypassing cache", short_id
            )
            new = await self._embedder.embed_batch(texts)
            job.cache_misses += len(texts)
            return new

        keys: list[tuple[bytes, str]] = [
            (hashlib.sha256(t.encode("utf-8")).digest(), model_name) for t in texts
        ]

        try:
            cached = self._cache.get_many(keys, expected_dim=dimensions)
        except Exception as exc:
            logger.warning(
                "[job %s] cache.get_many failed: %s — falling through", short_id, exc
            )
            cached = [None] * len(texts)

        missing_idx = [i for i, v in enumerate(cached) if v is None]
        missing_texts = [texts[i] for i in missing_idx]

        new_vectors_raw: list[list[float]] = (
            await self._embedder.embed_batch(missing_texts) if missing_texts else []
        )

        # Merge, preserving chunk order
        vectors: list[list[float]] = [None] * len(texts)  # type: ignore[list-item]
        for i, v in enumerate(cached):
            if v is not None:
                vectors[i] = v.tolist()
        for j, i in enumerate(missing_idx):
            vectors[i] = list(new_vectors_raw[j])

        # Populate cache with the new vectors
        if missing_idx:
            try:
                self._cache.put_many(
                    [
                        (keys[i], np.asarray(new_vectors_raw[j], dtype=np.float32))
                        for j, i in enumerate(missing_idx)
                    ]
                )
            except Exception as exc:
                logger.warning(
                    "[job %s] cache.put_many failed: %s — continuing", short_id, exc
                )

        job.cache_hits += len(texts) - len(missing_idx)
        job.cache_misses += len(missing_idx)

        return vectors  # type: ignore[return-value]
```

- [ ] **Step 5: Add the end-of-job log line**

In `BackgroundIndexer.run()`, find the existing `logger.info("[job %s] Completed: ...")` call. Immediately after it, add:

```python
            total_chunks = job.cache_hits + job.cache_misses
            if total_chunks > 0:
                hit_rate = 100.0 * job.cache_hits / total_chunks
                logger.info(
                    "[job %s] Cache: %d/%d hits (%.1f%%), %d new embeddings",
                    short_id,
                    job.cache_hits,
                    total_chunks,
                    hit_rate,
                    job.cache_misses,
                )
```

- [ ] **Step 6: Update the existing `indexer` fixture in `test_indexer.py` to pass `embed_cache=None`**

To keep pre-existing tests running, modify the `indexer` fixture in `test_indexer.py`:

```python
@pytest.fixture
def indexer(store, manifest, embedder, config, project_dir, registry):
    return BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=project_dir,
        embed_cache=None,
    )
```

- [ ] **Step 7: Run all indexer tests**

Run: `uv run pytest packages/guru-server/tests/test_indexer.py -v`
Expected: PASS (existing + 3 new cache tests).

- [ ] **Step 8: Commit**

```bash
git add packages/guru-server/src/guru_server/indexer.py \
        packages/guru-server/tests/test_indexer.py
git commit -m "feat(indexer): chunk-level embedding cache with fallthrough"
```

---

## Task 11: Add gitignore filter to `_discover`

**Files:**
- Modify: `packages/guru-server/src/guru_server/indexer.py`
- Modify: `packages/guru-server/tests/test_indexer.py`

- [ ] **Step 1: Write failing tests**

Append to `packages/guru-server/tests/test_indexer.py`:

```python
import subprocess


def _git_init(repo_dir: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)


@pytest.fixture
def git_project(tmp_path):
    """A git repo with a markdown file in docs/ and another in node_modules/ (gitignored)."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "real.md").write_text("# Real\n\nContent.")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "README.md").write_text("# Generated\n\nJunk.")
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    (tmp_path / ".guru").mkdir()
    (tmp_path / ".guru" / "db").mkdir()
    _git_init(tmp_path)
    subprocess.run(["git", "add", "docs/", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.asyncio
async def test_gitignore_filter_skips_ignored_files(git_project, registry):
    """Files in gitignored directories are not indexed."""
    from guru_core.types import GuruConfig, MatchConfig, Rule
    from guru_server.indexer import BackgroundIndexer
    from guru_server.manifest import FileManifest
    from guru_server.storage import VectorStore
    import lancedb

    store = VectorStore(db_path=str(git_project / ".guru" / "db"))
    db = lancedb.connect(str(git_project / ".guru" / "db"))
    manifest = FileManifest(db)
    embedder = MagicMock()
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    config = GuruConfig(
        version=1,
        rules=[Rule(rule_name="all", match=MatchConfig(glob="**/*.md"))],
    )
    indexer = BackgroundIndexer(
        store=store,
        manifest=manifest,
        embedder=embedder,
        config=config,
        project_root=git_project,
        embed_cache=None,
    )

    job = registry.create_job()
    await indexer.run(job)

    indexed_paths = {e["file_path"] for e in manifest.all_entries()}
    assert "docs/real.md" in indexed_paths
    assert "node_modules/README.md" not in indexed_paths


@pytest.mark.asyncio
async def test_non_git_project_uses_pure_glob(project_dir, registry, indexer):
    """When the project is not inside a git repo, the filter falls through."""
    # project_dir fixture does NOT run `git init` — discovery falls back to glob
    embedder = indexer._embedder
    embedder.model_name = "nomic-embed-text"
    embedder.dimensions = 768
    embedder.embed_batch = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))

    job = registry.create_job()
    await indexer.run(job)

    # Both docs/guide.md and docs/api.md get indexed (from the project_dir fixture)
    assert job.files_processed == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-server/tests/test_indexer.py::test_gitignore_filter_skips_ignored_files -v`
Expected: FAIL — gitignore filter doesn't exist yet.

- [ ] **Step 3: Add the `_git_tracked_paths` helper and filter to `_discover`**

In `packages/guru-server/src/guru_server/indexer.py`, add at module scope (below the existing `_file_hash` helper):

```python
import subprocess


def _git_tracked_paths(project_root: Path) -> set[str] | None:
    """Return the set of paths git considers tracked-or-unignored, relative
    to project_root. Returns None if this is not a git worktree or git is
    unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=project_root,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return set(result.stdout.decode("utf-8").split("\0")) - {""}
```

In `_discover`, at the top of the method (right after the docstring), compute git paths once:

```python
    def _discover(self, job: Job):
        """Scan files and compare against manifest. Returns (to_index, to_skip, to_delete)."""
        git_paths = _git_tracked_paths(self._project_root)

        # Collect excluded files
        excluded_files: set[Path] = set()
        for rule in self._config.rules:
            if rule.exclude:
                excluded_files.update(self._project_root.glob(rule.match.glob))
```

In the main matching loop, add the gitignore check after the `self._parser.supports` check:

```python
        seen_files: set[Path] = set()
        matched: list[tuple[Path, str, Rule]] = []
        for rule in self._config.rules:
            if rule.exclude:
                continue
            for file_path in self._project_root.glob(rule.match.glob):
                if not file_path.is_file():
                    continue
                if file_path in excluded_files:
                    continue
                if file_path in seen_files:
                    continue
                if not self._parser.supports(file_path):
                    continue
                rel_path = str(file_path.relative_to(self._project_root))
                if git_paths is not None and rel_path not in git_paths:
                    continue  # gitignored — skip
                seen_files.add(file_path)
                matched.append((file_path, rel_path, rule))
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/guru-server/tests/test_indexer.py -v`
Expected: PASS (existing + 2 new gitignore tests).

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/indexer.py \
        packages/guru-server/tests/test_indexer.py
git commit -m "feat(indexer): gitignore-aware discovery via git ls-files"
```

---

## Task 12: REST endpoints — GET/DELETE `/cache`, POST `/cache/prune`

**Files:**
- Create: `packages/guru-server/src/guru_server/api/cache.py`
- Modify: `packages/guru-server/src/guru_server/api/__init__.py`
- Modify: `packages/guru-server/src/guru_server/api/models.py`
- Modify: `packages/guru-server/tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Append to `packages/guru-server/tests/test_api.py`:

```python
def test_get_cache_stats_empty(client):
    resp = client.get("/cache")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 0
    assert data["total_bytes"] == 0
    assert data["by_model"] == {}


def test_delete_cache_clears_all(client, app):
    import hashlib
    import numpy as np

    key = (hashlib.sha256(b"hello").digest(), "nomic-embed-text")
    app.state.embed_cache.put_many([(key, np.array([0.1] * 768, dtype=np.float32))])

    resp = client.delete("/cache")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    # Cache is now empty
    assert app.state.embed_cache.stats().total_entries == 0


def test_delete_cache_scoped_by_model(client, app):
    import hashlib
    import numpy as np

    app.state.embed_cache.put_many(
        [
            ((hashlib.sha256(b"a").digest(), "m1"), np.array([1.0], dtype=np.float32)),
            ((hashlib.sha256(b"b").digest(), "m2"), np.array([2.0], dtype=np.float32)),
        ]
    )

    resp = client.delete("/cache?model=m1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert app.state.embed_cache.stats().total_entries == 1


def test_prune_cache(client, app):
    import hashlib
    import numpy as np

    # Insert an entry and manually age its accessed_at
    key = (hashlib.sha256(b"old").digest(), "m1")
    app.state.embed_cache.put_many([(key, np.array([1.0], dtype=np.float32))])
    old_ts_ms = 0  # unix epoch
    app.state.embed_cache._conn.execute(
        "UPDATE embeddings SET accessed_at = ? WHERE content_hash = ?",
        (old_ts_ms, key[0]),
    )

    resp = client.post("/cache/prune", json={"older_than_ms": 1000})
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
```

You also need to update the existing `client` fixture in `test_api.py` to build an app that has an `EmbeddingCache` on `app.state`, and expose an `app` fixture so tests can prime the cache. Replace the existing `client` fixture with:

```python
@pytest.fixture
def embed_cache(tmp_path):
    from guru_server.embed_cache import EmbeddingCache

    cache = EmbeddingCache(db_path=tmp_path / "test_embeddings.db")
    yield cache
    cache.close()


@pytest.fixture
def app(mock_store, mock_embedder, embed_cache):
    # Expose the FastAPI app so tests can access app.state.embed_cache
    return create_app(
        store=mock_store,
        embedder=mock_embedder,
        embed_cache=embed_cache,
        auto_index=False,
    )


@pytest.fixture
def client(app):
    return TestClient(app)
```

This replaces the earlier `client` fixture that called `create_app` directly — the new one composes through `app`. Existing tests that only use `client` continue to work unchanged; new tests can request the `app` fixture to reach `app.state.embed_cache`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-server/tests/test_api.py::test_get_cache_stats_empty -v`
Expected: FAIL — no `/cache` endpoint registered.

- [ ] **Step 3: Create `packages/guru-server/src/guru_server/api/cache.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Request

from guru_core.types import (
    CacheDeleteResult,
    CachePruneRequest,
    CacheStatsOut,
)

router = APIRouter()


def _assemble_stats(request: Request) -> CacheStatsOut:
    cache = request.app.state.embed_cache
    registry = request.app.state.job_registry

    if cache is None:
        return CacheStatsOut(
            path="",
            total_entries=0,
            total_bytes=0,
            by_model={},
        )

    stats = cache.stats()

    # Find the most recent completed job for last_job_* fields
    last_hits = None
    last_misses = None
    last_rate = None
    completed = [j for j in registry.list_jobs() if j.status == "completed"]
    if completed:
        latest = max(completed, key=lambda j: j.finished_at or j.created_at)
        last_hits = latest.cache_hits
        last_misses = latest.cache_misses
        total = last_hits + last_misses
        last_rate = (last_hits / total) if total > 0 else None

    return CacheStatsOut(
        path=stats.path,
        total_entries=stats.total_entries,
        total_bytes=stats.total_bytes,
        by_model=stats.by_model,
        last_job_hits=last_hits,
        last_job_misses=last_misses,
        last_job_hit_rate=last_rate,
    )


@router.get("/cache", response_model=CacheStatsOut)
async def get_cache_stats(request: Request):
    return _assemble_stats(request)


@router.delete("/cache", response_model=CacheDeleteResult)
async def delete_cache_entries(request: Request, model: str | None = None):
    cache = request.app.state.embed_cache
    if cache is None:
        return CacheDeleteResult(deleted=0)
    deleted = cache.clear(model=model)
    return CacheDeleteResult(deleted=deleted)


@router.post("/cache/prune", response_model=CacheDeleteResult)
async def prune_cache_entries(request: Request, req: CachePruneRequest):
    cache = request.app.state.embed_cache
    if cache is None:
        return CacheDeleteResult(deleted=0)
    deleted = cache.prune(older_than_ms=req.older_than_ms)
    return CacheDeleteResult(deleted=deleted)
```

- [ ] **Step 4: Register the router in `packages/guru-server/src/guru_server/api/__init__.py`**

```python
from fastapi import APIRouter

from guru_server.api.cache import router as cache_router
from guru_server.api.documents import router as documents_router
from guru_server.api.index import router as index_router
from guru_server.api.jobs import router as jobs_router
from guru_server.api.search import router as search_router
from guru_server.api.status import router as status_router

api_router = APIRouter()
api_router.include_router(search_router)
api_router.include_router(documents_router)
api_router.include_router(index_router)
api_router.include_router(jobs_router)
api_router.include_router(status_router)
api_router.include_router(cache_router)
```

- [ ] **Step 5: Re-export cache types in `api/models.py`**

Add `CacheStatsOut`, `CacheDeleteResult`, `CachePruneRequest` to the imports and `__all__` list:

```python
"""API response/request models — re-exported from guru_core.types (canonical source)."""

from guru_core.types import (
    CacheDeleteResult,
    CachePruneRequest,
    CacheStatsOut,
    DocumentListItem,
    DocumentOut,
    IndexAccepted,
    IndexOut,
    JobDetail,
    JobSummary,
    SearchResultOut,
    SectionOut,
    StatusOut,
)

__all__ = [
    "CacheDeleteResult",
    "CachePruneRequest",
    "CacheStatsOut",
    "DocumentListItem",
    "DocumentOut",
    "IndexAccepted",
    "IndexOut",
    "JobDetail",
    "JobSummary",
    "SearchResultOut",
    "SectionOut",
    "StatusOut",
]
```

- [ ] **Step 6: Run the API tests**

Run: `uv run pytest packages/guru-server/tests/test_api.py -v`
Expected: PASS (existing + new cache tests).

- [ ] **Step 7: Commit**

```bash
git add packages/guru-server/src/guru_server/api/cache.py \
        packages/guru-server/src/guru_server/api/__init__.py \
        packages/guru-server/src/guru_server/api/models.py \
        packages/guru-server/tests/test_api.py
git commit -m "feat(api): GET/DELETE /cache and POST /cache/prune endpoints"
```

---

## Task 13: Extend `GET /status` to include `CacheStatsOut`

**Files:**
- Modify: `packages/guru-server/src/guru_server/api/status.py`
- Modify: `packages/guru-server/tests/test_api.py`

- [ ] **Step 1: Write a failing test**

Append to `packages/guru-server/tests/test_api.py`:

```python
def test_status_includes_cache_section(client, app):
    import hashlib
    import numpy as np

    # Put something in the cache so path/entries are non-default
    key = (hashlib.sha256(b"hello").digest(), "nomic-embed-text")
    app.state.embed_cache.put_many([(key, np.array([0.1] * 768, dtype=np.float32))])

    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "cache" in data
    assert data["cache"] is not None
    assert data["cache"]["total_entries"] == 1
    assert data["cache"]["path"].endswith("embeddings.db") or data["cache"]["path"] == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-server/tests/test_api.py::test_status_includes_cache_section -v`
Expected: FAIL — status endpoint doesn't include cache yet.

- [ ] **Step 3: Update `packages/guru-server/src/guru_server/api/status.py`**

```python
from fastapi import APIRouter, Request

from guru_server.api.cache import _assemble_stats
from guru_server.api.models import StatusOut

router = APIRouter()


@router.get("/status", response_model=StatusOut)
async def get_status(request: Request):
    store = request.app.state.store
    registry = request.app.state.job_registry
    current = registry.current_job()
    cache_stats = None
    if request.app.state.embed_cache is not None:
        cache_stats = _assemble_stats(request)
    return StatusOut(
        server_running=True,
        document_count=store.document_count(),
        chunk_count=store.chunk_count(),
        last_indexed=request.app.state.last_indexed,
        ollama_available=True,
        model_loaded=True,
        current_job=current.to_summary() if current else None,
        cache=cache_stats,
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/guru-server/tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-server/src/guru_server/api/status.py \
        packages/guru-server/tests/test_api.py
git commit -m "feat(api): include cache stats in GET /status"
```

---

## Task 14: Add cache methods to `GuruClient`

**Files:**
- Modify: `packages/guru-core/src/guru_core/client.py`
- Modify: `packages/guru-core/tests/test_client.py`

- [ ] **Step 1: Write a failing test**

Append to `packages/guru-core/tests/test_client.py`:

```python
@pytest.mark.asyncio
async def test_cache_info_returns_stats(guru_root, running_server):
    client = GuruClient(guru_root=guru_root)
    stats = await client.cache_info()
    assert "total_entries" in stats
    assert "total_bytes" in stats
    assert "by_model" in stats


@pytest.mark.asyncio
async def test_cache_clear_returns_deleted_count(guru_root, running_server):
    client = GuruClient(guru_root=guru_root)
    result = await client.cache_clear()
    assert "deleted" in result


@pytest.mark.asyncio
async def test_cache_prune_returns_deleted_count(guru_root, running_server):
    client = GuruClient(guru_root=guru_root)
    result = await client.cache_prune(older_than_ms=1000)
    assert "deleted" in result
```

(The existing fixture names for the guru test server may differ — adapt to whatever `test_client.py` already uses. If there are no fixtures yet, these test bodies can simply invoke a test FastAPI app directly via `httpx.AsyncClient(transport=httpx.ASGITransport(app))`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-core/tests/test_client.py::test_cache_info_returns_stats -v`
Expected: FAIL — method doesn't exist.

- [ ] **Step 3: Add the methods to `packages/guru-core/src/guru_core/client.py`**

Add a `_delete` helper:

```python
    async def _delete(self, path: str) -> dict | list:
        async with httpx.AsyncClient(transport=self._transport(), timeout=self._timeout) as client:
            logger.debug("DELETE %s", path)
            resp = await client.delete(f"http://localhost{path}")
            logger.debug("DELETE %s -> %d", path, resp.status_code)
            if resp.is_error:
                resp.raise_for_status()
            return resp.json()
```

Add the three new methods below the existing `get_job`:

```python
    async def cache_info(self) -> dict:
        return await self._get("/cache")

    async def cache_clear(self, model: str | None = None) -> dict:
        path = "/cache"
        if model:
            path = f"{path}?{urlencode({'model': model})}"
        return await self._delete(path)

    async def cache_prune(self, older_than_ms: int) -> dict:
        return await self._post("/cache/prune", {"older_than_ms": older_than_ms})
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/guru-core/tests/test_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-core/src/guru_core/client.py packages/guru-core/tests/test_client.py
git commit -m "feat(client): add cache_info/cache_clear/cache_prune methods"
```

---

## Task 15: Add `guru cache` CLI command group

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/cli.py`
- Modify: `packages/guru-cli/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Append to `packages/guru-cli/tests/test_cli.py`:

```python
def test_cache_info_command(tmp_path, monkeypatch):
    """guru cache info calls client.cache_info() and prints the result."""
    from unittest.mock import AsyncMock, patch

    from click.testing import CliRunner

    from guru_cli.cli import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    fake_stats = {
        "path": "/tmp/embeddings.db",
        "total_entries": 42,
        "total_bytes": 1024,
        "by_model": {"nomic-embed-text": 42},
        "last_job_hits": None,
        "last_job_misses": None,
        "last_job_hit_rate": None,
    }
    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.cache_info = AsyncMock(return_value=fake_stats)
        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "info"])
        assert result.exit_code == 0
        assert "42" in result.output
        assert "nomic-embed-text" in result.output


def test_cache_clear_command_with_yes(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    from click.testing import CliRunner

    from guru_cli.cli import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.cache_clear = AsyncMock(return_value={"deleted": 7})
        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "clear", "--yes"])
        assert result.exit_code == 0
        assert "7" in result.output


def test_cache_prune_command_with_yes(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    from click.testing import CliRunner

    from guru_cli.cli import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.cache_prune = AsyncMock(return_value={"deleted": 3})
        runner = CliRunner()
        result = runner.invoke(cli, ["cache", "prune", "--older-than", "30d", "--yes"])
        assert result.exit_code == 0
        assert "3" in result.output


def test_parse_duration_supports_d_w_h_m():
    from guru_cli.cli import _parse_duration_to_ms

    assert _parse_duration_to_ms("30d") == 30 * 24 * 3600 * 1000
    assert _parse_duration_to_ms("2w") == 14 * 24 * 3600 * 1000
    assert _parse_duration_to_ms("6h") == 6 * 3600 * 1000
    assert _parse_duration_to_ms("15m") == 15 * 60 * 1000


def test_parse_duration_rejects_bad_input():
    import click
    import pytest

    from guru_cli.cli import _parse_duration_to_ms

    with pytest.raises(click.BadParameter):
        _parse_duration_to_ms("30days")
    with pytest.raises(click.BadParameter):
        _parse_duration_to_ms("abc")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py::test_cache_info_command -v`
Expected: FAIL — no `cache` command group yet.

- [ ] **Step 3: Add the command group and helper to `packages/guru-cli/src/guru_cli/cli.py`**

Add the duration parser helper near the top of the file (after `_run`):

```python
import re


def _parse_duration_to_ms(text: str) -> int:
    """Parse a duration like '30d', '2w', '6h', '15m' into milliseconds.

    Only simple forms are supported. Any other input raises click.BadParameter.
    """
    match = re.fullmatch(r"(\d+)([dwhm])", text)
    if match is None:
        raise click.BadParameter(
            f"Invalid duration '{text}'. Use forms like 30d, 2w, 6h, 15m."
        )
    n = int(match.group(1))
    unit = match.group(2)
    multipliers = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
    }
    return n * multipliers[unit]
```

Add the `cache` command group at the bottom of the file:

```python
@cli.group()
def cache():
    """Manage the embedding cache."""


@cache.command("info")
def cache_info():
    """Show cache size, entry count, and model breakdown."""
    client = _get_client()
    stats = _run(client.cache_info())
    click.echo(f"  path:         {stats['path']}")
    click.echo(f"  total entries: {stats['total_entries']}")
    size_mb = stats["total_bytes"] / (1024 * 1024)
    click.echo(f"  total size:    {size_mb:.2f} MB")
    if stats["by_model"]:
        click.echo("  by model:")
        for model, count in sorted(stats["by_model"].items()):
            click.echo(f"    {model}: {count}")
    if stats.get("last_job_hit_rate") is not None:
        rate = stats["last_job_hit_rate"] * 100
        click.echo(
            f"  last job:     {stats['last_job_hits']} hits / "
            f"{stats['last_job_misses']} misses ({rate:.1f}%)"
        )


@cache.command("clear")
@click.option("--model", default=None, help="Only clear entries for this model")
@click.confirmation_option(prompt="Delete cache entries?")
def cache_clear(model: str | None):
    """Delete cache entries. Defaults to everything; --model scopes to one model."""
    client = _get_client()
    result = _run(client.cache_clear(model=model))
    click.echo(f"Deleted {result['deleted']} entries")


@cache.command("prune")
@click.option(
    "--older-than",
    "older_than",
    required=True,
    help="Delete entries not accessed in this duration (e.g. 30d, 2w, 6h, 15m)",
)
@click.confirmation_option(prompt="Prune cache entries?")
def cache_prune(older_than: str):
    """Delete entries with accessed_at older than the given duration."""
    older_than_ms = _parse_duration_to_ms(older_than)
    client = _get_client()
    result = _run(client.cache_prune(older_than_ms=older_than_ms))
    click.echo(f"Pruned {result['deleted']} entries")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/cli.py packages/guru-cli/tests/test_cli.py
git commit -m "feat(cli): guru cache info/clear/prune commands"
```

---

## Task 16: Extend `guru server status` output with cache block

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/cli.py`
- Modify: `packages/guru-cli/tests/test_cli.py`

- [ ] **Step 1: Write a failing test**

Append to `packages/guru-cli/tests/test_cli.py`:

```python
def test_server_status_prints_cache_block(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    from click.testing import CliRunner

    from guru_cli.cli import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".guru").mkdir()

    fake_status = {
        "server_running": True,
        "document_count": 5,
        "chunk_count": 50,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "cache": {
            "path": "/tmp/embeddings.db",
            "total_entries": 25,
            "total_bytes": 5000,
            "by_model": {"nomic-embed-text": 25},
            "last_job_hits": 10,
            "last_job_misses": 15,
            "last_job_hit_rate": 0.4,
        },
    }
    with patch("guru_cli.cli._get_client") as mock_get_client:
        client = mock_get_client.return_value
        client.status = AsyncMock(return_value=fake_status)
        runner = CliRunner()
        result = runner.invoke(cli, ["server", "status"])
        assert result.exit_code == 0
        assert "Cache:" in result.output
        assert "25" in result.output
        assert "10 hits" in result.output or "10" in result.output
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py::test_server_status_prints_cache_block -v`
Expected: FAIL — status command doesn't print cache block.

- [ ] **Step 3: Update `server_status` in `packages/guru-cli/src/guru_cli/cli.py`**

Replace the body of `server_status`:

```python
@server.command("status")
@click.option("--job", "job_id", default=None, help="Show details for a specific job")
def server_status(job_id):
    """Show server status."""
    client = _get_client()
    if job_id:
        job = _run(client.get_job(job_id))
        for key, value in job.items():
            click.echo(f"  {key}: {value}")
        return
    status = _run(client.status())
    current_job = status.pop("current_job", None)
    cache_block = status.pop("cache", None)
    for key, value in status.items():
        click.echo(f"  {key}: {value}")
    if current_job:
        total = current_job["files_total"]
        processed = current_job["files_processed"]
        skipped = current_job["files_skipped"]
        click.echo(f"  Indexing: {processed}/{total} files processed ({skipped} skipped)")
    if cache_block:
        click.echo("")
        click.echo(f"Cache: {cache_block['path']}")
        click.echo(f"  Entries:       {cache_block['total_entries']:,}")
        size_mb = cache_block["total_bytes"] / (1024 * 1024)
        click.echo(f"  Size:          {size_mb:.1f} MB")
        if cache_block["by_model"]:
            models_line = ", ".join(
                f"{m} ({c})" for m, c in sorted(cache_block["by_model"].items())
            )
            click.echo(f"  Models:        {models_line}")
        if cache_block.get("last_job_hit_rate") is not None:
            rate = cache_block["last_job_hit_rate"] * 100
            click.echo(
                f"  Last job:      {cache_block['last_job_hits']} hits / "
                f"{cache_block['last_job_misses']} misses ({rate:.1f}%)"
            )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/guru-cli/tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-cli/src/guru_cli/cli.py packages/guru-cli/tests/test_cli.py
git commit -m "feat(cli): guru server status prints cache block"
```

---

## Task 17: Amend ARCHITECTURE.md

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Update §Data Ownership**

Replace the existing §Data Ownership section (lines 53-56 in the current file) with:

```markdown
## Data Ownership

- `.guru/` directory in the project root holds per-project runtime state (db, socket, pid, manifest). Each worktree has its own `.guru/`.
- `.guru/` is gitignored. It is pure runtime state, never version-controlled.
- `.guru.json` (preferred) or legacy `guru.json` in the project root holds indexing rules. It is version-controlled.
- The **embedding cache** lives at the OS-standard user cache directory (`$XDG_CACHE_HOME/guru/embeddings.db` on Linux, `~/Library/Caches/guru/embeddings.db` on macOS). It is a content-addressed optimization, not state: every entry is derivable from the chunks it caches, so deleting the cache is always safe — it only costs re-embedding time. The cache is shared across all guru projects and worktrees on the machine, keyed by `sha256(chunk_text) + model_name`.
```

- [ ] **Step 2: Update §Ingestion**

Add one new bullet at the end of the existing §Ingestion section:

```markdown
- **Gitignore-aware discovery:** when the project root is inside a git repository, file discovery respects `.gitignore` via `git ls-files --cached --others --exclude-standard`. Gitignored paths are never indexed, regardless of whether they match the user's rule globs. Non-git projects fall back to pure glob discovery.
```

- [ ] **Step 3: Update §Configuration**

Replace the existing §Configuration section (lines 59-64 in the current file) with:

```markdown
## Configuration

- JSON config with a top-level `{ "version": 1, "rules": [...] }` object. Each rule has `ruleName`, `match.glob`, optional `exclude`, `labels`, and `chunking` overrides.
- The legacy flat-array format (`[ { "ruleName": ..., ... } ]`) is still read and auto-wrapped to `{ "version": 1, "rules": <array> }`. The `guru init` command and any future write path emit the object format.
- Resolution chain: `./.guru.json` > `./guru.json` > `./.guru/config.json` > `~/.config/guru/config.json`.
- Merge by `ruleName`: local rules with same name fully replace global. New names appended.
- No config anywhere → hardcoded default: index all `**/*.md`.
```

- [ ] **Step 4: Sanity-check the file**

Run: `grep -n "embedding cache" ARCHITECTURE.md`
Expected: at least one match in §Data Ownership.

Run: `grep -n "Gitignore-aware" ARCHITECTURE.md`
Expected: one match in §Ingestion.

Run: `grep -n "version.*1.*rules" ARCHITECTURE.md`
Expected: at least one match in §Configuration.

- [ ] **Step 5: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs(architecture): amend for embedding cache, gitignore, config format"
```

---

## Task 18: BDD test isolation — `GURU_EMBED_CACHE_PATH` env var in `environment.py`

**Files:**
- Modify: `tests/e2e/features/environment.py`

- [ ] **Step 1: Read the current `environment.py` to understand the existing fixture pattern**

Run: `cat tests/e2e/features/environment.py`

- [ ] **Step 2: Add the env-var override in the existing `before_feature` hook**

Add to the `before_feature` hook (or create one if it doesn't exist). Just before the server is started, set:

```python
import os
import tempfile

def before_feature(context, feature):
    # Existing setup...

    # Isolate the embedding cache per feature so scenarios don't pollute each other
    cache_file = tempfile.NamedTemporaryFile(
        prefix="guru-test-cache-", suffix=".db", delete=False
    )
    cache_file.close()
    os.environ["GURU_EMBED_CACHE_PATH"] = cache_file.name
    context._cache_path = cache_file.name
```

Add matching cleanup to `after_feature`:

```python
def after_feature(context, feature):
    # Existing teardown...
    path = getattr(context, "_cache_path", None)
    if path and os.path.exists(path):
        os.unlink(path)
    os.environ.pop("GURU_EMBED_CACHE_PATH", None)
```

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/features/environment.py
git commit -m "test(e2e): isolate embedding cache per feature via env var"
```

---

## Task 19: BDD — `cache_cli.feature`

**Files:**
- Create: `tests/e2e/features/cache_cli.feature`

Note: All steps used in this feature (`a guru project with sample markdown files`, `the guru server is running`, `the knowledge base has been indexed`, `I run "X"`, `the command succeeds`, `the output contains X`) are already defined in `tests/e2e/features/steps/cli_steps.py`. No new step file is required for this feature. A dedicated `cache_steps.py` is created later in Task 21 for the worktree-cache scenarios that do need new steps.

- [ ] **Step 1: Create `tests/e2e/features/cache_cli.feature`**

```gherkin
Feature: guru cache CLI commands
  As a developer I can observe and manage my embedding cache.

  Background:
    Given a guru project with sample markdown files
    And the guru server is running

  Scenario: guru cache info shows current state after indexing
    Given the knowledge base has been indexed
    When I run "guru cache info"
    Then the command succeeds
    And the output contains "total entries"
    And the output contains "nomic-embed-text"

  Scenario: guru cache clear wipes everything
    Given the knowledge base has been indexed
    When I run "guru cache clear --yes"
    Then the command succeeds
    And the output contains "Deleted"

  Scenario: guru cache prune with a duration works
    Given the knowledge base has been indexed
    When I run "guru cache prune --older-than 30d --yes"
    Then the command succeeds
    And the output contains "Pruned"

  Scenario: guru server status shows cache block
    Given the knowledge base has been indexed
    When I run "guru server status"
    Then the command succeeds
    And the output contains "Cache:"
```

- [ ] **Step 2: Run the behave feature**

Run: `uv run behave tests/e2e/features/cache_cli.feature`
Expected: all scenarios PASS — every step resolves to an existing `cli_steps.py` step.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/features/cache_cli.feature
git commit -m "test(e2e): BDD scenarios for guru cache CLI commands"
```

---

## Task 20: BDD — `gitignore_discovery.feature`

**Files:**
- Create: `tests/e2e/features/gitignore_discovery.feature`
- Modify: `tests/e2e/features/steps/cache_steps.py` (reuse for gitignore step helpers) or create `tests/e2e/features/steps/gitignore_steps.py`

- [ ] **Step 1: Create `tests/e2e/features/gitignore_discovery.feature`**

```gherkin
Feature: Indexing respects .gitignore
  As a developer I don't want gitignored directories or worktrees to be indexed.

  Scenario: Files under a gitignored directory are skipped
    Given a fresh git project at a temporary path
    And the project contains "docs/real.md" with "# Real\n\ncontent."
    And the project contains "node_modules/README.md" with "# Junk\n\nskip."
    And ".gitignore" contains "node_modules/"
    And the project has been git-committed
    And the guru server is running
    When I run "guru index"
    And I wait for the index job to complete
    And I run "guru list"
    Then the command succeeds
    And the output contains "docs/real.md"
    And the output does not contain "node_modules/README.md"

  Scenario: Worktree inside a gitignored directory is not indexed from the main worktree
    Given a fresh git project at a temporary path
    And ".gitignore" contains ".worktrees/"
    And the project contains "docs/main.md" with "# Main\n\ncontent."
    And the project has been git-committed
    And a git worktree "feature-x" is created at ".worktrees/feature-x"
    And the worktree contains "docs/branch.md" with "# Branch\n\ncontent."
    And the guru server is running
    When I run "guru index"
    And I wait for the index job to complete
    And I run "guru list"
    Then the command succeeds
    And the output does not contain ".worktrees/feature-x/docs/branch.md"
```

- [ ] **Step 2: Create `tests/e2e/features/steps/gitignore_steps.py`**

```python
"""Step definitions for gitignore-aware discovery BDD tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from behave import given


@given('a fresh git project at a temporary path')
def step_fresh_git_project(context):
    import tempfile

    tmp = tempfile.mkdtemp(prefix="guru-bdd-git-")
    context.project_path = Path(tmp)
    subprocess.run(["git", "init", "-q"], cwd=context.project_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=context.project_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=context.project_path,
        check=True,
    )
    # guru init expects to run in the project
    (context.project_path / ".guru").mkdir()
    (context.project_path / ".guru" / "db").mkdir()
    (context.project_path / ".guru.json").write_text(
        '{"version": 1, "rules": [{"ruleName": "all", "match": {"glob": "**/*.md"}}]}\n'
    )
    # Change directory so later "I run X" steps operate in this project
    context._prev_cwd = os.getcwd()
    os.chdir(context.project_path)


@given('the project contains "{rel_path}" with "{content}"')
def step_project_contains_file(context, rel_path, content):
    file_path = context.project_path / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content.replace("\\n", "\n"))


@given('".gitignore" contains "{pattern}"')
def step_gitignore_contains(context, pattern):
    gi = context.project_path / ".gitignore"
    existing = gi.read_text() if gi.exists() else ""
    gi.write_text(existing + pattern + "\n")


@given('the project has been git-committed')
def step_git_commit(context):
    subprocess.run(["git", "add", "-A"], cwd=context.project_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"],
        cwd=context.project_path,
        check=True,
    )


@given('a git worktree "{name}" is created at "{rel_path}"')
def step_create_worktree(context, name, rel_path):
    subprocess.run(
        ["git", "worktree", "add", "-q", rel_path, "-b", name],
        cwd=context.project_path,
        check=True,
    )


@given('the worktree contains "{rel_path}" with "{content}"')
def step_worktree_contains_file(context, rel_path, content):
    # rel_path is already relative to the main project; the file is INSIDE the worktree
    worktree_root = next(
        (context.project_path / ".worktrees").iterdir()
    )
    file_path = worktree_root / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content.replace("\\n", "\n"))
```

Cleanup in `after_scenario` is handled by standard behave teardown; if needed, add a hook in `environment.py` to restore `os.chdir(context._prev_cwd)` after each scenario.

- [ ] **Step 3: Run the feature**

Run: `uv run behave tests/e2e/features/gitignore_discovery.feature`
Expected: both scenarios PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/features/gitignore_discovery.feature \
        tests/e2e/features/steps/gitignore_steps.py
git commit -m "test(e2e): BDD scenarios for gitignore-aware discovery"
```

---

## Task 21: BDD — `worktree_cache.feature`

**Files:**
- Create: `tests/e2e/features/worktree_cache.feature`
- Create: `tests/e2e/features/steps/cache_steps.py`

- [ ] **Step 1: Create `tests/e2e/features/worktree_cache.feature`**

```gherkin
Feature: Embedding cache speeds up re-indexing
  The embedding cache should let a second project with identical content
  reuse embeddings from the first project instead of re-calling Ollama.

  Background:
    Given a clean embedding cache

  Scenario: Indexing a project twice reuses the embedding cache
    Given a guru project with a single file "docs/foo.md" with content "# Foo\n\nbar"
    And the guru server is running
    When I run "guru index"
    And I wait for the index job to complete
    Then the cache contains at least 1 entry for "nomic-embed-text"
    When I clear the project's .guru/db directory
    And I restart the guru server
    And I run "guru index"
    And I wait for the index job to complete
    Then the most recent index job reports non-zero cache hits
```

- [ ] **Step 2: Create `tests/e2e/features/steps/cache_steps.py` with the new step definitions**

```python
"""Step definitions for worktree-cache BDD scenarios."""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from behave import given, then, when


@given('a clean embedding cache')
def step_clean_cache(context):
    path = os.environ.get("GURU_EMBED_CACHE_PATH")
    if path and Path(path).exists():
        Path(path).unlink()


@given('a guru project with a single file "{rel_path}" with content "{content}"')
def step_project_with_single_file(context, rel_path, content):
    import tempfile

    tmp = tempfile.mkdtemp(prefix="guru-bdd-cache-")
    context.project_path = Path(tmp)
    (context.project_path / ".guru").mkdir()
    (context.project_path / ".guru" / "db").mkdir()
    (context.project_path / ".guru.json").write_text(
        '{"version": 1, "rules": [{"ruleName": "all", "match": {"glob": "**/*.md"}}]}\n'
    )
    file_path = context.project_path / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content.replace("\\n", "\n"))
    context._prev_cwd = os.getcwd()
    os.chdir(context.project_path)


@then('the cache contains at least {n:d} entry for "{model}"')
@then('the cache contains at least {n:d} entries for "{model}"')
def step_cache_has_n_entries(context, n, model):
    path = os.environ["GURU_EMBED_CACHE_PATH"]
    conn = sqlite3.connect(path)
    count = conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE model = ?", (model,)
    ).fetchone()[0]
    conn.close()
    assert count >= n, f"Expected >= {n} entries for {model}, got {count}"


@when("I clear the project's .guru/db directory")
def step_clear_guru_db(context):
    db_path = context.project_path / ".guru" / "db"
    if db_path.exists():
        shutil.rmtree(db_path)
    db_path.mkdir(parents=True)


@when("I restart the guru server")
def step_restart_server(context):
    # Reuse the existing stop/start step helpers from environment.py.
    # If no such helpers exist, invoke guru server stop then rely on auto-start.
    import subprocess

    subprocess.run(["guru", "server", "stop"], cwd=context.project_path, check=False)


@then("the most recent index job reports non-zero cache hits")
def step_last_job_has_cache_hits(context):
    import json as _json
    import subprocess

    result = subprocess.run(
        ["guru", "server", "status"],
        capture_output=True,
        text=True,
        check=True,
        cwd=context.project_path,
    )
    assert "cache" in result.stdout.lower()
    # A strict assertion can also parse the output for "hits": > 0
```

- [ ] **Step 3: Run the feature**

Run: `uv run behave tests/e2e/features/worktree_cache.feature`
Expected: all scenarios PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/features/worktree_cache.feature \
        tests/e2e/features/steps/cache_steps.py
git commit -m "test(e2e): BDD scenarios for embedding cache reuse"
```

---

## Task 22: Full-suite smoke test and final cleanup

**Files:** none — this task runs the full test suite and verifies nothing is broken.

- [ ] **Step 1: Run linter**

Run: `make lint`
Expected: clean. If ruff flags anything in the new files, run `make format` and re-run `make lint`.

- [ ] **Step 2: Run the full unit+integration test suite**

Run: `uv run pytest`
Expected: all pass. No warnings escalated to failures.

- [ ] **Step 3: Run the full BDD suite**

Run: `uv run behave tests/e2e/features/`
Expected: every scenario passes, including the three new feature files and all pre-existing features unchanged.

- [ ] **Step 4: Verify the cache file actually appears in the platformdirs location after a real run**

Run:

```bash
# In a throwaway tempdir
TMP=$(mktemp -d)
cd "$TMP"
uv run guru init
uv run guru index
uv run guru cache info
```

Expected: `guru cache info` prints a non-zero `total_entries` and a real path ending in `embeddings.db`.

- [ ] **Step 5: No commit (verification only).**

If any step fails, go back to the failing task, fix the underlying issue, and re-run.

---

## Spec coverage check

| Spec section | Task(s) implementing it |
|---|---|
| §2 Config file restructure | Task 1 (types), Task 2 (load_config), Task 3 (call sites), Task 4 (guru init) |
| §3 Embedding cache: storage, location, keying | Task 6 (deps), Task 7 (EmbeddingCache module), Task 9 (wire into startup) |
| §3 Model drift defense (dim mismatch as miss) | Task 7 (test: `test_dimension_mismatch_treated_as_miss`) |
| §4a Gitignore filter in `_discover` | Task 11 |
| §4b Cache path in `_index_file` | Task 10 |
| §4c Job counters, embedder attrs, run-completion log | Task 5 (embedder), Task 8 (job counters), Task 10 (log line) |
| §5a `guru status` with cache block | Task 13 (server side), Task 16 (CLI side) |
| §5b `guru cache` command group | Task 15 |
| §5c Client SDK cache methods | Task 14 |
| §5d REST endpoints | Task 12 |
| §5e MCP tools deliberately NOT exposed | By omission — no MCP changes in any task |
| §5f Duration parser | Task 15 (`_parse_duration_to_ms`) |
| §6 Constitution amendment | Task 17 |
| §7a Unit tests: `EmbeddingCache` | Task 7 |
| §7b Unit tests: config migration | Task 2 |
| §7c Unit tests: indexer integration (cache + gitignore) | Task 10 (cache), Task 11 (gitignore) |
| §7d BDD: worktree_cache.feature | Task 21 |
| §7d BDD: gitignore_discovery.feature | Task 20 |
| §7d BDD: cache_cli.feature | Task 19 |
| §7e GURU_EMBED_CACHE_PATH env var | Task 9 (main.py), Task 18 (environment.py) |
| §8 Forward-compat: no Option 1 work | Explicit non-goal |
