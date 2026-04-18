.DEFAULT_GOAL := help

PACKAGES := packages/guru-core packages/guru-server packages/guru-mcp packages/guru-cli packages/guru-graph

# ─── Help ────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo "Guru — local-first knowledge-base manager"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Setup"
	@echo "  install            Install all workspace packages (uv sync --all-packages)"
	@echo ""
	@echo "Testing"
	@echo "  test               Unit + integration tests (fast, no e2e)"
	@echo "  test-unit          Unit tests across all packages"
	@echo "  test-integration   Integration tests (tests/)"
	@echo "  test-e2e           BDD e2e tests (serial)"
	@echo "  test-e2e-parallel  BDD e2e tests (parallel, one process per feature)"
	@echo "  test-all           All tests: unit + integration + e2e"
	@echo "  test-graph         Graph plugin tests including @real_neo4j (requires Neo4j)"
	@echo "  test-graph-local   Spin up ephemeral Neo4j, run all @real_neo4j tests, tear down"
	@echo ""
	@echo "Build"
	@echo "  build              Build all 5 wheels into dist/"
	@echo "  build-index        Build wheels then generate PEP 503 index into dist/simple/"
	@echo ""
	@echo "Code quality"
	@echo "  lint               Check code style (ruff check)"
	@echo "  fmt                Auto-fix lint issues and format code"
	@echo "  format             Alias for fmt"
	@echo ""
	@echo "Maintenance"
	@echo "  clean              Remove dist/, build/, caches, and egg-info directories"

# ─── Setup ───────────────────────────────────────────────────────────────────

.PHONY: install
install:
	uv sync --all-packages

# ─── Testing ─────────────────────────────────────────────────────────────────

.PHONY: test-unit
test-unit:
	uv run pytest packages/ -v --tb=short

.PHONY: test-integration
test-integration:
	uv run pytest tests/ -v --tb=short

.PHONY: test-e2e
test-e2e:
	uv run behave tests/e2e/features/

.PHONY: test-e2e-parallel
test-e2e-parallel:
	./scripts/run-behave-parallel.sh

.PHONY: test
test: test-unit test-integration

.PHONY: test-all
test-all: test-unit test-integration test-e2e

.PHONY: test-graph
test-graph:
	GURU_REAL_NEO4J=1 uv run pytest packages/guru-graph/ -v --tb=short
	GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/graph_plugin.feature

# Spin up an ephemeral Neo4j 5 container, run all @real_neo4j-tagged tests
# (pytest + every BDD feature that depends on a live daemon), then tear down —
# even on failure. Wipes Neo4j between BDD features to prevent state bleed
# (e.g. KBs created by graph_plugin.feature leaking into graph_cli_reads.feature
# count assertions). Requires Docker.
.PHONY: test-graph-local
test-graph-local:
	@./scripts/start-test-neo4j.sh
	@trap 'docker rm -f guru-graph-test-neo4j >/dev/null 2>&1 || true' EXIT; \
	 set -e; \
	 export GURU_NEO4J_BOLT_URI=bolt://127.0.0.1:17687 GURU_REAL_NEO4J=1; \
	 wipe() { docker exec guru-graph-test-neo4j cypher-shell -d neo4j 'MATCH (n) DETACH DELETE n;' >/dev/null; }; \
	 uv run pytest packages/guru-graph/ -v --tb=short; \
	 wipe; uv run behave tests/e2e/features/graph_plugin.feature; \
	 wipe; uv run behave tests/e2e/features/graph_cli_reads.feature; \
	 wipe; uv run behave tests/e2e/features/annotations_and_curation.feature --tags=~@skip_until_pr5 --tags=~@skip_until_pr7; \
	 wipe; uv run behave tests/e2e/features/orphan_triage.feature --tags=~@skip_until_pr7; \
	 wipe; uv run behave tests/e2e/features/artifact_indexing.feature --tags=~@skip_until_pr7 --tags=~@skip_until_pr8

# ─── Build ───────────────────────────────────────────────────────────────────

.PHONY: build
build:
	@mkdir -p dist
	@for pkg in $(PACKAGES) .; do \
		uv build --directory $$pkg --out-dir "$$(pwd)/dist/"; \
	done
	@echo "All wheels written to dist/"

.PHONY: build-index
build-index: build
	uv run python scripts/generate_index.py dist/ dist/simple/
	@echo "PEP 503 index written to dist/simple/"

# ─── Code quality ────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	uv run ruff check .
	uv run ruff format --check .

.PHONY: fmt format
fmt format:
	uv run ruff check --fix .
	uv run ruff format .

# ─── Maintenance ─────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	rm -rf dist/ build/
	find . -type d -name __pycache__ -not -path './.git/*' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -not -path './.git/*' -exec rm -rf {} +
	find . -type d -name .pytest_cache -not -path './.git/*' -exec rm -rf {} +
	@echo "Clean complete."
