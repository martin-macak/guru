# Test Strategy Sandbox Compatibility Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the default test suite fast, reliable, Docker-free, and runnable in restricted local/remote sandboxes while keeping a smaller opt-in compatibility layer for real Neo4j, real Ollama, and real socket/process smoke coverage.

**Architecture:** Treat in-process app tests (`TestClient`, `FastMCP Client`, `CliRunner`, `FakeBackend`) as the required path. Move UDS bind, loopback port, Neo4j, and Ollama coverage into clearly marked opt-in compatibility suites. Align GitHub CI so required jobs exercise the same fast path developers and remote agents can run.

**Tech Stack:** `pytest`, `behave`, `FastAPI TestClient`, `httpx`, `FastMCP Client`, `click.testing.CliRunner`, `guru_graph.testing.FakeBackend`, optional external Neo4j/Ollama jobs.

---

### Task 1: Fix CI Coverage Gaps First

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `Makefile`
- Test: `tests/test_integration.py`
- Test: `tests/test_packaging.py`

- [ ] **Step 1: Add a required root-tests job**

Run the root suite independently in CI instead of only package-scoped pytest:

```yaml
  root-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"
      - run: uv sync --all-packages
      - run: uv run pytest tests/ -v --tb=short
```

- [ ] **Step 2: Expand the change detector**

Make `detect-changes` watch shared files that affect every package test run:

```yaml
            shared:
              - 'pyproject.toml'
              - 'uv.lock'
              - 'Makefile'
              - 'tests/**'
              - '.github/workflows/**'
```

If `shared` changes, run all required test jobs.

- [ ] **Step 3: Fix the Ollama-capability mismatch**

The current CI job installs Ollama but runs:

```bash
uv run behave tests/e2e/features/
```

That does not enable the `ollama` capability. Either:

```bash
uv run behave tests/e2e/features/ -D capabilities=ollama
```

or remove the Ollama install from the default e2e job and run semantic search in a separate optional job.

- [ ] **Step 4: Split required vs optional graph coverage in CI**

Keep the default PR path container-free. Move service-container coverage behind an explicit job name such as:

```yaml
graph-compat:
```

and document it as optional compatibility coverage rather than part of the default fast suite.

- [ ] **Step 5: Verify the pipeline locally**

Run:

```bash
uv run pytest tests/ -v --tb=short
uv run pytest packages/ -q -k 'not test_allocate_free_port_returns_usable'
```

Expected: root tests are exercised explicitly and the fast pytest path matches CI.

### Task 2: Create a Sandbox-Safe Guru Server Test Harness

**Files:**
- Modify: `tests/e2e/features/environment.py`
- Modify: `tests/e2e/features/steps/cli_steps.py`
- Modify: `tests/e2e/features/steps/mcp_steps.py`
- Modify: `tests/e2e/features/steps/background_indexing_steps.py`
- Modify: `tests/e2e/features/steps/cache_steps.py`
- Modify: `tests/e2e/features/steps/gitignore_steps.py`
- Modify: `tests/e2e/features/steps/federation_steps.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Introduce an in-process app transport helper**

Add a helper that builds:

```python
app = create_app(...)
client = TestClient(app)
```

and returns lightweight adapters for:
- REST calls
- `GuruClient`-shaped method calls
- CLI command execution against the in-memory app when possible

- [ ] **Step 2: Stop requiring `uvicorn.Server(..., uds=...)` for default BDD**

Replace the default `before_feature` path with the in-process helper for features that currently call `_start_server(...)`.

Do not delete the real UDS helper yet; keep it only for the future compatibility suite.

- [ ] **Step 3: Patch MCP steps to use an injected in-process client**

`tests/e2e/features/steps/mcp_steps.py` already patches `guru_mcp.server._get_client`. Replace:

```python
return GuruClient(guru_root=project_dir)
```

with a fake or adapter client backed by the in-process server, following the pattern already used in `graph_mcp_tools_steps.py`.

- [ ] **Step 4: Convert CLI-heavy BDD to `CliRunner` where transport realism is not the point**

For scenarios asserting command output and behavior rather than auto-start/socket wiring, use `CliRunner.invoke(...)` or a thin adapter instead of spawning `uv run guru`.

Keep only one explicit compatibility smoke test for the real autostart/UDS path.

- [ ] **Step 5: Verify sandbox-safe BDD**

Run:

```bash
uv run behave tests/e2e/features/knowledge_base.feature
uv run behave tests/e2e/features/mcp_tools.feature
uv run behave tests/e2e/features/background_indexing.feature
```

Expected: these no longer depend on binding `.guru/guru.sock`.

### Task 3: Remove Unnecessary Daemon Use From Default Graph BDD

**Files:**
- Modify: `tests/e2e/features/annotations_and_curation.feature`
- Modify: `tests/e2e/features/artifact_links.feature`
- Modify: `tests/e2e/features/steps/annotation_steps.py`
- Modify: `tests/e2e/features/steps/relates_steps.py`
- Modify: `tests/e2e/features/steps/graph_steps.py`

- [ ] **Step 1: Fix the feature/spec mismatch**

The step modules claim the invalid-body/invalid-kind scenarios are FakeBackend-only, but the feature files still say:

```gherkin
Given a running guru-graph daemon
```

Change those scenarios to a fake-app setup step, for example:

```gherkin
Given a FakeBackend-backed graph app
```

- [ ] **Step 2: Reuse the existing fake helpers**

Promote the `_fake_app()` / `_seeded_test_client()` helpers into shared helpers so multiple step files can use them without duplicating backend bootstraps.

- [ ] **Step 3: Keep real-daemon behavior behind `@real_neo4j` only**

Any scenario that still needs:

```python
connect_or_spawn(paths=paths, ready_timeout_seconds=60.0)
```

must be explicitly tagged `@real_neo4j` or moved to a separate compatibility feature file.

- [ ] **Step 4: Verify the formerly slow failure cases**

Run:

```bash
uv run behave tests/e2e/features/annotations_and_curation.feature --tags='~@real_neo4j'
uv run behave tests/e2e/features/artifact_links.feature --tags='~@real_neo4j'
```

Expected: both finish in seconds instead of waiting on daemon startup timeouts.

### Task 4: Reclassify Real-Service Coverage as Compatibility Tests

**Files:**
- Modify: `packages/guru-graph/tests/conftest.py`
- Modify: `packages/guru-graph/tests/test_config_paths.py`
- Modify: `tests/e2e/features/capabilities.py`
- Modify: `scripts/start-test-neo4j.sh`
- Modify: `Makefile`

- [ ] **Step 1: Add an explicit compatibility marker family**

Introduce markers such as:

```toml
"compat_socket: requires binding AF_UNIX or loopback sockets"
"compat_neo4j: requires a real Neo4j backend"
"compat_ollama: requires a real Ollama instance"
```

Use them for tests that cannot be made transport-free.

- [ ] **Step 2: Rework `test_allocate_free_port_returns_usable`**

The current test performs a real loopback bind. Replace it with one of:
- a monkeypatched socket allocation test
- a `compat_socket` marker
- a graceful skip on `PermissionError`

The default fast suite should not fail because a sandbox blocks `127.0.0.1:0`.

- [ ] **Step 3: Make Docker purely optional**

Keep `scripts/start-test-neo4j.sh` as a convenience wrapper, but do not make it part of the required path. The contract should be:
- default suite: no Docker
- compatibility suite: caller supplies Docker, native Neo4j, or external Bolt URI

- [ ] **Step 4: Add explicit compatibility commands**

Document commands such as:

```bash
uv run pytest -m 'not compat_socket and not real_neo4j'
uv run pytest -m compat_socket
GURU_REAL_NEO4J=1 GURU_NEO4J_BOLT_URI=bolt://localhost:7687 uv run pytest packages/guru-graph/ -m real_neo4j
```

### Task 5: Improve Fast-Path Test Performance

**Files:**
- Modify: `tests/e2e/features/environment.py`
- Modify: `tests/e2e/features/steps/background_indexing_steps.py`
- Modify: `tests/test_integration.py`
- Modify: `packages/guru-server/tests/test_indexer.py`
- Modify: `packages/guru-server/tests/test_api.py`

- [ ] **Step 1: Remove long polling defaults from fast-path failures**

Current default-suite failure cost is dominated by:
- `guru-server did not start within 10 s`
- `connect_or_spawn(... ready_timeout_seconds=60.0)`

For fast-path suites, use shorter deadlines or no daemon/socket startup at all.

- [ ] **Step 2: Reuse expensive fixtures**

The slowest pytest files are concentrated in `guru-server` because they repeatedly build storage/app state. Extract shared fixtures for:
- seeded `VectorStore`
- seeded app/TestClient
- deterministic embedder

Prefer function-level isolation only where state mutation requires it.

- [ ] **Step 3: Keep serial pytest as the default**

Measured baseline on this workspace:

```text
serial: 714 passed, 12 skipped, 1 deselected in 6.85s
xdist:  725 passed, 12 skipped in 12.03s
```

Do not enable `-n auto` by default for the fast suite.

- [ ] **Step 4: Shorten integration polling**

`tests/test_integration.py` polls `/status` in a loop. Prefer waiting on job completion directly or using shorter intervals/timeouts once the in-process harness is stable.

- [ ] **Step 5: Re-measure and capture the new baseline**

Run:

```bash
uv run pytest packages/ tests/ -q
uv run behave tests/e2e/features/ --tags='~@real_neo4j' --tags='~@real_ollama'
```

Record:
- total wall time
- top 20 slowest pytest tests
- per-feature behave wall time
- skipped compatibility count

### Task 6: Keep One Thin End-to-End Compatibility Layer

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `Makefile`
- Modify: `tests/e2e/features/graph_plugin.feature`
- Modify: `tests/e2e/features/graph_cli_reads.feature`
- Modify: `tests/e2e/features/semantic_search.feature`

- [ ] **Step 1: Define the minimal compatibility matrix**

Keep only the following as opt-in compatibility coverage:
- real Neo4j backend contract
- graph daemon/socket smoke
- real Ollama semantic retrieval smoke
- optional CLI autostart over UDS smoke

- [ ] **Step 2: Reduce BDD compatibility scope**

Do not run the full 19-feature behave suite in compatibility mode. Run only the features that truly exercise environment integration.

- [ ] **Step 3: Gate compatibility jobs intentionally**

Use labels, nightly schedules, or manual dispatch for the container/service jobs. Required PR checks should remain sandbox-safe and container-free.

- [ ] **Step 4: Publish the new contract**

Update repo docs so contributors know:
- `make test` is fast and Docker-free
- compatibility jobs are opt-in
- remote agents can run the required suite inside restricted sandboxes

