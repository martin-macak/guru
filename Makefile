.DEFAULT_GOAL := help

PACKAGES := packages/guru-core packages/guru-server packages/guru-mcp packages/guru-cli

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
	@echo ""
	@echo "Build"
	@echo "  build              Build all 5 wheels into dist/"
	@echo "  build-index        Build wheels then generate PEP 503 index into dist/simple/"
	@echo ""
	@echo "Code quality"
	@echo "  lint               Check code style (not configured yet)"
	@echo "  fmt                Format code (not configured yet)"
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
	@echo "Linting is not configured yet. Add ruff or flake8 to get started."

.PHONY: fmt
fmt:
	@echo "Formatting is not configured yet. Add ruff format or black to get started."

# ─── Maintenance ─────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	rm -rf dist/ build/
	find . -type d -name __pycache__ -not -path './.git/*' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -not -path './.git/*' -exec rm -rf {} +
	find . -type d -name .pytest_cache -not -path './.git/*' -exec rm -rf {} +
	@echo "Clean complete."
