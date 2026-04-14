# Worktree Speed via Content-Addressed Embedding Cache

**Issue:** #26 — Git worktree support: shared or inherited index
**Date:** 2026-04-14
**Status:** Draft

---

## Problem

When a developer creates a new git worktree of an already-indexed Guru project, the new worktree has no `.guru/` (it's gitignored), so indexing starts from scratch — every markdown chunk is re-embedded via Ollama even though the vast majority of documents are byte-identical to those already indexed in another worktree of the same repo. On realistic projects this re-embed takes minutes.

Additionally, today's file discovery walks `project_root.glob(...)` without consulting `.gitignore`. That means `node_modules/`, `.venv/`, build artifacts, and — critically — worktree directories created inside a gitignored path of the main repo (e.g. `.worktrees/feature-x/`) are all traversed and indexed.

Finally, the `guru.json` config file is currently a flat JSON array of rules. There is nowhere to add any new configuration without making it worse, which blocks every option on the table for solving worktree speed.

## Goals

1. **Primary:** Creating a new git worktree of an already-indexed project should reach "first successful search" in ≤10 seconds for a typical (~200 markdown file) project, down from minutes.
2. Indexing must respect `.gitignore` when the project is inside a git repository. Gitignored paths are never indexed, regardless of whether they match the user's rule globs.
3. Migrate the config file from a flat JSON array to a proper object with a top-level `version` field, keeping the legacy array form readable via auto-wrap.
4. The cache must be observable (`guru status`) and manageable (`guru cache info|clear|prune`).
5. No correctness regressions: every existing BDD scenario passes unchanged.

## Non-Goals

- **Not** sharing `.guru/db` across worktrees. Each worktree keeps its own LanceDB and manifest. Correctness is per-worktree; there is no "main worktree pinning" magic. (This is Option 1 in issue #26 and is deferred as a future opt-in — see §8.)
- **Not** solving per-branch overlay indexes (Option 4 in the issue). Explicitly deferred.
- **Not** automatic LRU eviction. The cache grows unbounded; the user manages it via CLI.
- **No** cross-project cache isolation. The cache is shared across all guru-indexed projects on the machine — the content hash is the identity. This is a feature, not a leak.
- **Not** exposing cache management via the MCP protocol. Cache ops are developer-facing, not agent-facing.
- **Not** eagerly rewriting existing `guru.json` files on disk. Legacy array format is read-compatible via auto-wrap; `guru init` and any future write path emit the new object format.

---

## Approach

The expensive part of indexing is the Ollama `embed_batch` call. Chunking (LlamaIndex `MarkdownNodeParser`), SHA-256 hashing, and LanceDB inserts are all orders of magnitude faster. A content-addressed cache keyed on `sha256(chunk_text) + model_name` eliminates the slow step on repeated content and leaves everything else untouched.

Each worktree keeps its own `.guru/db` and manifest, so per-worktree correctness is automatic: branch-local edits to a doc are reflected in that worktree's search results. Only the expensive compute (embedding) is shared, via a global SQLite file at the OS cache directory.

This solves **speed (A)** from the brainstorming, explicitly accepts that disk usage **(C)** is not a priority, and defers per-branch correctness **(B)** to a future Option 1/4 PR if users ever request it.

---

## Section 1 — Components

Four packages touched:

- **guru-core** — new `GuruConfig` Pydantic model, new `CacheStatsOut` / `CacheDeleteResult` / `CachePruneRequest` types, new async client methods for the three REST endpoints.
- **guru-server** — new `embed_cache.py` module, indexer integration (cache path + gitignore filter), three new FastAPI endpoints, `platformdirs` dependency.
- **guru-cli** — new `guru cache` command group, `guru status` output extension.
- **guru-mcp** — **untouched.** Cache tools are deliberately not exposed via MCP.

---

## Section 2 — Config file restructure

### Current format (legacy)

```json
[
  {"ruleName": "default", "match": {"glob": "**/*.md"}}
]
```

### New format (v1)

```json
{
  "version": 1,
  "rules": [
    {"ruleName": "default", "match": {"glob": "**/*.md"}}
  ]
}
```

Deliberately minimal. `version` exists so the schema can evolve cleanly later. No other top-level fields ship in this PR — `indexDir`, cache tuning knobs, and everything else are explicit future hooks. Packing them in now would mean committing to shapes we don't yet have a use case for.

### Pydantic model (`guru_core/types.py`)

```python
class GuruConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: int = 1
    rules: list[Rule] = Field(default_factory=list)
```

### Read path (backwards compat)

`guru_core/config.py:load_rules` becomes `load_config`, returning `GuruConfig`:

```python
def load_config(path: Path) -> GuruConfig | None:
    if not path.is_file():
        return None
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"version": 1, "rules": data}
    return GuruConfig(**data)
```

One `isinstance` check is the entire migration on read.

### Write path

`guru init` at `guru-cli/cli.py:75` writes the new object form. Existing files on disk are **not** rewritten in place — that would be surprising under version control. They keep working via the read-path auto-wrap until the user themselves edits the file. `guru config migrate` can ship as a follow-up if anyone asks.

### API impact

- `load_rules` → renamed to `load_config`, returns `GuruConfig`.
- `resolve_config` → same name, now returns `GuruConfig` instead of `list[Rule]`.
- `merge_rules` → unchanged internal helper, still operates on `list[Rule]`.
- `DEFAULT_RULES` → stays as the fallback population for `config.rules`.
- Call sites that need the rule list pull `config.rules` off the object.

Touches: `guru-server/main.py:79`, `guru-server/app.py` (wherever config is stored on app state), `guru-server/indexer.py:33` constructor (`config: list[Rule]` → `config: GuruConfig`), and their tests. Shallow rename, no logic change.

### Legacy filename fallbacks

Chain preserved: `.guru.json` → `guru.json` → `.guru/config.json` → `~/.config/guru/config.json`.

### Explicitly left out of v1

- `$schema` URL — no schema site hosted
- `extends` / inheritance — unused
- `enabled` flag — rules can be deleted
- Per-rule priorities — array order already provides ordering

---

## Section 3 — Embedding cache: storage, location, and keying

### Location

```python
from platformdirs import user_cache_dir
cache_dir = Path(user_cache_dir("guru"))   # ~/Library/Caches/guru on macOS, ~/.cache/guru on Linux
db_path = cache_dir / "embeddings.db"
```

Adds `platformdirs` as a dependency of `guru-server` only. `guru-core` stays lightweight per ARCHITECTURE.md §Dependency Rules.

### Storage backend: SQLite, single table

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    content_hash   BLOB    NOT NULL,    -- sha256(chunk_text), 32 bytes
    model          TEXT    NOT NULL,    -- e.g. 'nomic-embed-text'
    dimensions     INTEGER NOT NULL,    -- 768 for nomic-embed-text
    vector         BLOB    NOT NULL,    -- float32 packed via numpy.tobytes()
    created_at     INTEGER NOT NULL,    -- unix ms, first insert
    accessed_at    INTEGER NOT NULL,    -- unix ms, updated on every hit
    PRIMARY KEY (content_hash, model)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model);
```

`WITHOUT ROWID` keeps composite-PK lookups fast and the file small. `accessed_at` is tracked so `guru cache prune --older-than` works without a schema migration.

**WAL mode.** `PRAGMA journal_mode=WAL` at open time. Multiple guru-server processes (from concurrent worktrees) will hit this file; WAL is the standard fix for multi-reader / single-writer SQLite.

### Cache key

```python
CacheKey = tuple[bytes, str]   # (sha256_digest, model_name)
```

Deliberately narrow:

- **Chunker parameters are NOT in the key.** The vector is a pure function of `(chunk_text, model)`. Two chunkers that happen to produce the same chunk text can legitimately share a vector. Including chunker params would fragment the cache for no correctness win.
- **Model is a plain string**, not a model digest. See "Model drift" below for why and how we defend against it.
- **No project ID, no worktree ID, no path.** Content identity is the entire identity. This is what makes cross-worktree (and cross-project) reuse work.

### Model drift defense

Ollama's `nomic-embed-text` is a tag that could, in principle, be re-pointed to a different model with different dimensions. We don't include a model digest in the cache key (too fragile), but we do defend against the dangerous failure mode by validating dimensions on read:

```python
def get(self, key: CacheKey, expected_dim: int) -> np.ndarray | None:
    row = self._conn.execute(
        "SELECT dimensions, vector FROM embeddings WHERE content_hash = ? AND model = ?",
        (key[0], key[1]),
    ).fetchone()
    if row is None:
        return None
    stored_dim, blob = row
    if stored_dim != expected_dim:
        return None   # treat as miss; next put_many will overwrite the row
    self._touch(key)
    return np.frombuffer(blob, dtype=np.float32)
```

Dimension mismatch → treat as miss → row gets silently overwritten on the next `put`. No corruption, no mystery. Low hit rate after a model change is exactly the signal a user wants to see.

### Python module

New file: `packages/guru-server/src/guru_server/embed_cache.py`.

```python
class EmbeddingCache:
    def __init__(self, db_path: Path): ...
    def get_many(self, keys: list[CacheKey], expected_dim: int) -> list[np.ndarray | None]: ...
    def put_many(self, entries: list[tuple[CacheKey, np.ndarray]]) -> None: ...
    def stats(self) -> CacheStats: ...                # count, bytes, by-model breakdown
    def clear(self, model: str | None = None) -> int: # returns rows deleted
    def prune(self, older_than_ms: int) -> int:       # returns rows deleted
```

Opened once at server startup, closed on shutdown. Lives on app state alongside `store` and `embedder`.

### Concurrency and error handling

- All cache calls are wrapped in a try/except that **logs and falls through to the embedder**. Cache corruption or a locked SQLite must never fail an indexing job.
- `put_many` is a single transaction with `INSERT OR REPLACE`. If two processes race to cache the same key, last-writer-wins and they're identical anyway.
- `get_many` uses a single `IN (...)` query, not N individual selects.

### Not in v1

- Automatic LRU eviction (`accessed_at` exists but is unused by v1)
- Vector compression (dense floats; zstd would save ~15% at CPU cost)
- Multi-machine sharing
- Import/export

---

## Section 4 — Indexer integration: cache path + gitignore filter

Two changes land in `packages/guru-server/src/guru_server/indexer.py`, both in the same PR.

### 4a. Gitignore filter in `_discover`

New helper at module scope:

```python
def _git_tracked_paths(project_root: Path) -> set[str] | None:
    """Return paths git considers tracked-or-unignored, relative to project_root.
    Returns None if this is not a git worktree."""
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

**Why `git ls-files` and not a Python gitignore library:**

- Correctness for free — git is the source of truth for what's ignored. Any Python reimplementation will drift.
- Worktree-aware natively. In a worktree inside a gitignored dir (`.worktrees/feature-x/`), running `git ls-files` from that worktree lists that worktree's own files. Running it from the main worktree does NOT descend into `.worktrees/` because it's gitignored.
- Fast (sub-second even on large repos) and one subprocess call per indexing job.
- Unix-only is fine — Guru is macOS/Linux per CLAUDE.md.

`_discover` gets one new filter step, inserted after the glob + exclude + seen-files checks:

```python
git_paths = _git_tracked_paths(self._project_root)   # None if non-git

for rule in self._config.rules:
    if rule.exclude: continue
    for file_path in self._project_root.glob(rule.match.glob):
        # existing is_file / excluded / seen / supports checks
        rel_path = str(file_path.relative_to(self._project_root))
        if git_paths is not None and rel_path not in git_paths:
            continue   # gitignored — skip
        matched.append((file_path, rel_path, rule))
```

**Non-git projects are unaffected.** If `git_paths is None`, the filter is a no-op and behavior matches today.

**Deletion semantics are preserved.** The `to_delete` logic at `indexer.py:157` compares manifest entries against `matched_rel_paths`. When a user adds a `.gitignore` entry that matches previously-indexed files, those files drop out of `matched_rel_paths` on the next run and get removed from the index automatically. No special migration code.

### 4b. Cache path in `_index_file`

Current:

```python
texts = [chunk.content for chunk in chunks]
vectors = await self._embedder.embed_batch(texts)
self._store.delete_file(rel_path)
self._store.add_chunks(chunks, vectors)
```

New:

```python
texts = [chunk.content for chunk in chunks]
keys = [(sha256(t.encode()).digest(), self._embedder.model_name) for t in texts]

try:
    cached = self._cache.get_many(keys, expected_dim=self._embedder.dimensions)
except Exception as exc:
    logger.warning("[job %s] cache.get_many failed: %s — falling through", short_id, exc)
    cached = [None] * len(texts)

missing_idx = [i for i, v in enumerate(cached) if v is None]
missing_texts = [texts[i] for i in missing_idx]

new_vectors = (await self._embedder.embed_batch(missing_texts)) if missing_texts else []

# Merge, preserving chunk order (critical for add_chunks correspondence)
vectors = list(cached)
for j, i in enumerate(missing_idx):
    vectors[i] = new_vectors[j]

try:
    self._cache.put_many([(keys[i], new_vectors[j]) for j, i in enumerate(missing_idx)])
except Exception as exc:
    logger.warning("[job %s] cache.put_many failed: %s — continuing", short_id, exc)

job.cache_hits += len(chunks) - len(missing_idx)
job.cache_misses += len(missing_idx)

self._store.delete_file(rel_path)
self._store.add_chunks(chunks, vectors)
```

Key invariants:

1. **The cache is never a dependency.** Every cache call is in a try/except that logs and falls through. A corrupted SQLite file or a locked DB must never fail an indexing job.
2. **Order preservation.** `chunks[i]` must correspond to `vectors[i]` before `add_chunks`. That's why we merge into a pre-sized list.
3. **Nothing is written to LanceDB until all embeddings are ready** — keeps the existing safety guarantee that parse/embed failures don't destroy the previous index.

### 4c. Supporting changes

- **`Job` model** (`guru-server/jobs.py`): add `cache_hits: int = 0` and `cache_misses: int = 0`.
- **`JobDetail` and `JobSummary`** (`guru-core/types.py`): surface `cache_hits` and `cache_misses` on the API schema.
- **`OllamaEmbedder`**: expose `model_name: str` and `dimensions: int` as attributes. Added in this PR if they don't already exist — the cache can't work without them.
- **`BackgroundIndexer.__init__`**: accept an `EmbeddingCache` instance and store it.
- **`guru-server/main.py:79`**: construct `EmbeddingCache(db_path=...)` alongside `store` and `embedder`, pass it into the app factory which passes it into the indexer.
- **Run-completion log**: one extra line at the end of `BackgroundIndexer.run()`:

  ```
  [job abc12345] Cache: 847/1002 hits (84.5%), 155 new embeddings
  ```

### 4d. Not touched

- `find_guru_root` — still walks up for `.guru/`. Git-aware discovery is Option 1, deferred.
- Manifest schema — still `rel_path → (content_hash, mtime, chunk_count)`. Cache hit/miss is orthogonal.
- LanceDB schema — unchanged.

---

## Section 5 — CLI surface: cache observability & management

All cache operations go through the server per ARCHITECTURE.md §Architecture (server owns all state).

### 5a. `guru status` additions

```python
class CacheStatsOut(BaseModel):
    path: str
    total_entries: int
    total_bytes: int
    by_model: dict[str, int]
    last_job_hits: int | None
    last_job_misses: int | None
    last_job_hit_rate: float | None

class StatusOut(BaseModel):
    # existing fields...
    cache: CacheStatsOut | None
```

CLI output adds a block at the bottom:

```
Cache: ~/Library/Caches/guru/embeddings.db
  Entries:       12,847
  Size:           47.3 MB
  Models:         nomic-embed-text (12,847)
  Last job:       847 hits / 155 misses (84.5%)
```

Nullable — the whole block is omitted if the cache file doesn't exist yet.

### 5b. `guru cache` command group

New click group in `packages/guru-cli/src/guru_cli/cli.py`:

```python
@cli.group()
def cache():
    """Manage the embedding cache."""

@cache.command("info")
def cache_info():
    """Show cache size, entry count, and model breakdown."""

@cache.command("clear")
@click.option("--model", default=None, help="Only clear entries for this model")
@click.confirmation_option(prompt="Delete cache entries?")
def cache_clear(model: str | None):
    """Delete cache entries. Defaults to everything; --model scopes to one model."""

@cache.command("prune")
@click.option("--older-than", required=True, help="Delete entries not accessed in this duration (e.g. 30d, 2w)")
@click.confirmation_option(prompt="Prune cache entries?")
def cache_prune(older_than: str):
    """Delete entries with accessed_at older than the given duration."""
```

Both `clear` and `prune` are destructive and get `@click.confirmation_option`, which supports `--yes` as an escape hatch.

### 5c. Client SDK additions

`packages/guru-core/src/guru_core/client.py` grows three async methods:

```python
async def cache_info(self) -> CacheStatsOut: ...
async def cache_clear(self, model: str | None = None) -> CacheDeleteResult: ...
async def cache_prune(self, older_than_ms: int) -> CacheDeleteResult: ...
```

### 5d. REST endpoints (FastAPI)

Three new endpoints in `packages/guru-server/src/guru_server/app.py`, all with `response_model` per CLAUDE.md:

```python
@app.get("/cache", response_model=CacheStatsOut)
async def get_cache_stats(): ...

@app.delete("/cache", response_model=CacheDeleteResult)
async def delete_cache_entries(model: str | None = None): ...

@app.post("/cache/prune", response_model=CacheDeleteResult)
async def prune_cache_entries(req: CachePruneRequest): ...
```

New Pydantic models in `guru_core/types.py`:

```python
class CacheDeleteResult(BaseModel):
    deleted: int

class CachePruneRequest(BaseModel):
    older_than_ms: int = Field(ge=0)
```

`POST /cache/prune` rather than `DELETE` because prune takes a body and HTTP `DELETE` with bodies is semantically iffy.

### 5e. MCP tools — deliberately NOT exposed

MCP tools normally map 1:1 to REST endpoints per ARCHITECTURE.md §MCP, but cache management is a developer-facing operation, not an agent-facing one. No LLM agent has any business running `guru cache clear`. The three endpoints above exist in the REST API and CLI but are **not** registered as MCP tools.

This is a deliberate exception to the 1:1 mapping rule and is called out in the design.

### 5f. Duration parsing for `--older-than`

Minimal: `Nd`, `Nw`, `Nh`, `Nm` only. No `30days` or `1 week` fanciness. Regex + multiply, ~10 lines. Invalid input → `click.BadParameter`.

---

## Section 6 — Constitutional amendment

Two sections of `ARCHITECTURE.md` need updates in the same PR as the design doc.

### 6a. §Data Ownership — clarify cache vs. state

Replace lines 53-56 with:

> ## Data Ownership
> - `.guru/` directory in the project root holds per-project runtime state (db, socket, pid, manifest). Each worktree has its own `.guru/`.
> - `.guru/` is gitignored. It is pure runtime state, never version-controlled.
> - `.guru.json` (preferred) or legacy `guru.json` in the project root holds indexing rules. It is version-controlled.
> - The **embedding cache** lives at the OS-standard user cache directory (`$XDG_CACHE_HOME/guru/embeddings.db` on Linux, `~/Library/Caches/guru/embeddings.db` on macOS). It is a content-addressed optimization, not state: every entry is derivable from the chunks it caches, so deleting the cache is always safe — it only costs re-embedding time. The cache is shared across all guru projects and worktrees on the machine, keyed by `sha256(chunk_text) + model_name`.

### 6b. §Ingestion — declare gitignore-awareness

Add one bullet to the existing ingestion section:

> - **Gitignore-aware discovery:** when the project root is inside a git repository, file discovery respects `.gitignore` via `git ls-files --cached --others --exclude-standard`. Gitignored paths are never indexed, regardless of whether they match the user's rule globs. Non-git projects fall back to pure glob discovery.

### 6c. §Configuration — note the object format

Replace lines 59-64 with:

> ## Configuration
> - JSON config with a top-level `{ "version": 1, "rules": [...] }` object. Each rule has `ruleName`, `match.glob`, optional `exclude`, `labels`, and `chunking` overrides.
> - The legacy flat-array format (`[ { "ruleName": ..., ... } ]`) is still read and auto-wrapped to `{ "version": 1, "rules": <array> }`. The `guru init` command and any future write path emit the object format.
> - Resolution chain: `./.guru.json` > `./guru.json` > `./.guru/config.json` > `~/.config/guru/config.json`.
> - Merge by `ruleName`: local rules with same name fully replace global. New names appended.
> - No config anywhere → hardcoded default: index all `**/*.md`.

---

## Section 7 — Testing strategy

### 7a. Unit tests — `EmbeddingCache`

New file: `packages/guru-server/tests/test_embed_cache.py`.

- Round-trip: put a vector, get it back, byte-identical after numpy round-trip
- Cache miss returns `None` for unknown keys
- `expected_dim` mismatch returns `None` even when the row exists (model-drift defense)
- `get_many` preserves input order and returns `None` in-place for misses
- `put_many` with `INSERT OR REPLACE` overwrites without raising
- `touch` updates `accessed_at` on every hit
- `clear(model=None)` deletes everything; `clear(model="nomic-embed-text")` scopes to one model
- `prune(older_than_ms=…)` respects `accessed_at`, not `created_at`
- `stats()` returns correct count, bytes, by-model breakdown
- WAL mode is enabled on open
- Concurrent reader/writer doesn't deadlock

### 7b. Unit tests — config migration

Extends `packages/guru-server/tests/test_config.py`:

- Legacy array loads → `GuruConfig(version=1, rules=<array>)`
- Object format loads → straight pass-through
- Empty array → `GuruConfig(rules=[])`, not an error
- Malformed JSON → raises same exception type as today
- `resolve_config` fallback chain unchanged

### 7c. Unit tests — indexer integration

Extends `packages/guru-server/tests/test_indexer.py`:

- Cache hit path: seed the cache, index a file, assert embedder's `embed_batch` was never called for cached chunks
- Cache miss path: empty cache, assert `embed_batch` was called for every chunk
- Mixed hit/miss: 3 chunks, 2 pre-cached, assert only the 1 missing chunk was embedded and order is preserved into `add_chunks`
- Cache `get_many` failure: mock raises, assert job completes and all chunks get embedded
- Cache `put_many` failure: mock raises, assert job completes and LanceDB still gets vectors
- Job counters: `job.cache_hits + job.cache_misses == chunks_created` at job end
- Gitignore filter: tempdir with `.gitignore` listing `ignored/`, create `docs/a.md` and `ignored/b.md`, assert only `docs/a.md` in manifest
- Non-git project unaffected: tempdir without `.git/`, assert behavior matches today

### 7d. BDD e2e — new scenarios

Per CLAUDE.md, feature files are part of the spec.

**`tests/e2e/features/worktree_cache.feature`**

```gherkin
Feature: Embedding cache speeds up re-indexing

  Background:
    Given a clean embedding cache
    And the embedder is a mock that records every call

  Scenario: Second project with identical content reuses cache
    Given project "alpha" with "docs/arch.md" containing the text "architecture overview"
    When I run guru index in "alpha"
    Then the embedder was called for every chunk
    And the cache contains 1 entry per chunk

    Given project "beta" with "docs/arch.md" containing the text "architecture overview"
    When I run guru index in "beta"
    Then the embedder was NOT called
    And beta's index contains the same chunks as alpha's

  Scenario: Model dimension mismatch triggers re-embed
    Given the cache contains a vector with dimensions 768 for the chunk "hello world"
    And the embedder produces vectors with dimensions 1024
    When I run guru index on a file containing only "hello world"
    Then the embedder IS called
    And the cache entry is overwritten with a 1024-dim vector
```

**`tests/e2e/features/gitignore_discovery.feature`**

```gherkin
Feature: Indexing respects .gitignore

  Scenario: Files under a gitignored directory are skipped
    Given a git project with:
      | path                    | content       |
      | docs/real.md            | real content  |
      | node_modules/README.md  | generated     |
      | .gitignore              | node_modules/ |
    When I run guru index
    Then the manifest contains "docs/real.md"
    And the manifest does not contain "node_modules/README.md"

  Scenario: Worktree created inside a gitignored directory is not indexed from the main worktree
    Given a git project with ".worktrees/" in .gitignore
    And a worktree at ".worktrees/feature-x" containing "docs/branch.md"
    When I run guru index from the main worktree
    Then the manifest does not contain ".worktrees/feature-x/docs/branch.md"

  Scenario: Non-git project still uses pure glob discovery
    Given a non-git project with "docs/foo.md" and "docs/bar.md"
    When I run guru index
    Then the manifest contains both files
```

**`tests/e2e/features/cache_cli.feature`**

```gherkin
Feature: guru cache CLI commands

  Scenario: guru cache info shows current state
    Given the cache contains 42 entries for "nomic-embed-text"
    When I run "guru cache info"
    Then the output contains "42 entries"
    And the output contains "nomic-embed-text (42)"

  Scenario: guru cache clear wipes everything
    Given the cache contains 100 entries
    When I run "guru cache clear --yes"
    Then the cache contains 0 entries

  Scenario: guru cache clear --model scopes to one model
    Given the cache contains 50 entries for "nomic-embed-text" and 20 for "other-model"
    When I run "guru cache clear --model nomic-embed-text --yes"
    Then the cache contains 20 entries for "other-model"
    And the cache contains 0 entries for "nomic-embed-text"

  Scenario: guru cache prune deletes entries by age
    Given the cache contains entries with accessed_at timestamps 60 days old and 10 days old
    When I run "guru cache prune --older-than 30d --yes"
    Then only the 10-day-old entries remain

  Scenario: guru status shows cache statistics
    Given the cache contains 25 entries
    When I run "guru status"
    Then the output contains "Cache:"
    And the output contains "25 entries"
```

### 7e. Test isolation

The BDD suite needs a clean cache per feature. Introduce a `GURU_EMBED_CACHE_PATH` env var that, when set, overrides the default `platformdirs.user_cache_dir(...)` path. Server respects the env var if set; falls back to `platformdirs` otherwise. The BDD `before_feature` hook points it at a tempfile. This composes with the existing `GURU_PROJECT_ROOT` pattern at `guru-server/main.py:64`.

### 7f. Not tested

- **Performance regression tests** — "cache must make indexing 10x faster" is a benchmarking concern, not a correctness test. Too flaky for CI. Lives under `@pytest.mark.slow` if we ever want one.
- **SQLite corruption recovery** — log-and-fall-through is already tested via the `get_many`/`put_many` failure scenarios. The underlying corruption is SQLite's problem.
- **Cross-project cache sharing as a security concern** — not a threat model worth testing. If you can read the cache file, you have filesystem access already.

---

## Section 8 — Forward-compatibility for Option 1 (deferred)

Option 1 from issue #26 (git-aware shared `.guru/` at the main worktree) ships later as an opt-in. This design leaves three hooks in place.

### 8a. Config has a reserved slot for `indexDir`

Deliberately **not** shipped in v1 — shipping unused fields trains users to wonder what they do. Option 1 will add `indexDir: str | None` to `GuruConfig` with `version: 1` still (new optional field, no migration).

### 8b. Discovery is the only place Option 1 needs to touch

`guru_core/discovery.py:find_guru_root` currently walks up for `.guru/`. Option 1 will change it to:

1. Walk up for `.guru/` (today's behavior — covers non-worktree users and the main worktree itself)
2. If not found, and the current directory is inside a git worktree, ask git for the main worktree path (`git rev-parse --path-format=absolute --git-common-dir` → parent) and check for `.guru/` there
3. Raise `GuruNotFoundError` only if both fail

Nothing else cares about how `.guru/` is located. Option 1's PR will be roughly:

- ~20 lines in `discovery.py`
- `indexDir` added to `GuruConfig` (overrides the discovery result when set)
- One BDD scenario for the git-aware walk-up
- Constitution amendment softening "each worktree has its own `.guru/`" to "by default, each worktree has its own `.guru/`"

No changes to indexer, cache, or CLI.

### 8c. What this design does NOT commit to

- No support for `indexExtraPaths` / union-scan (the M3 variant).
- No per-worktree overlay tables in LanceDB (Option 4 / full correctness).
- No cross-worktree manifest sharing.

If a future user asks for "shared `.guru/` AND per-branch correctness," that's a Section 4/overlay-indexing problem, not something a shared `.guru/` alone can solve. We revisit the design then.

---

## Open questions

None — all decisions made during brainstorming. See the section heading for each design call for the trade-offs considered.

## References

- Issue: #26 (guru)
- Related ARCHITECTURE.md sections: Data Ownership, Ingestion, Configuration, MCP
- Related code: `packages/guru-core/src/guru_core/config.py`, `packages/guru-server/src/guru_server/indexer.py`, `packages/guru-server/src/guru_server/main.py`, `packages/guru-core/src/guru_core/discovery.py`, `packages/guru-cli/src/guru_cli/cli.py`
