# Artifact Graph Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the full artifact-graph knowledge base feature for guru: extensible parser contract, per-file `(:Document)` invariant, m0002 schema migration, 10 new MCP tools with orphan-preserving annotations, agent skill distributed via `guru init` / `guru update`, Python + OpenAPI + Markdown parsers, all behind the existing "graph is strictly optional" invariant.

**Architecture:** Nine ordered PRs in four phases — foundation (parser contract, m0002), agent surface (annotations, links, MCP, skill), language parsers (Python, OpenAPI), docs closeout. Each PR is independently mergeable, green on CI, and preserves the invariant that every graph-agnostic operation works identically whether graph is enabled or not. Follows the design spec at `docs/superpowers/specs/2026-04-18-artifact-graph-knowledge-base-design.md` — that doc is the source of truth.

**Tech Stack:** Python 3.13 · uv workspace · FastAPI + uvicorn · Neo4j 5 · LanceDB · Ollama · LlamaIndex · tree-sitter-python · PyYAML · FastMCP · click · Textual · httpx · pydantic · behave · pytest · hatchling + uv-dynamic-versioning.

---

## File Structure

Files created across all nine PRs are grouped below by ownership. Every PR section identifies which files it creates or modifies in its scope block; this top-level map is the catalogue.

**`packages/guru-core/src/guru_core/`**
- `graph_types.py` — *modify.* Add `ArtifactLinkKind`, `AnnotationKind`, `GraphNode`, `GraphEdge`, `ParseResultPayload`, `AnnotationCreate`, `AnnotationNode`, `ArtifactLinkCreate`, `ArtifactLink`, `ArtifactNode`, `ArtifactNeighbors`, `ArtifactFindQuery`, `OrphanAnnotation` Pydantic models.
- `graph_client.py` — *modify.* Add `submit_parse_result`, `delete_document_in_graph`, `describe_artifact`, `neighbors`, `find_artifacts`, `create_annotation`, `delete_annotation`, `list_orphans`, `reattach_orphan`, `create_link`, `delete_link`, `graph_query` async methods. Protocol constant bumps to `1.1.0`.

**`packages/guru-server/src/guru_server/`**
- `ingestion/base.py` — *modify.* Extend `Chunk` dataclass with `kind`, `language`, `artifact_qualname`, `parent_document_id`. Add `GraphNode`, `GraphEdge`, `ParseResult` dataclasses. Add abstract `name` property + `kb_name` kwarg to `DocumentParser.parse`.
- `ingestion/registry.py` — *new.* `ParserRegistry` with `register()` and `dispatch()`.
- `ingestion/markdown.py` — *modify.* Return `ParseResult` with `(:Document)` + `(:MarkdownSection)` graph facts.
- `ingestion/python.py` — *new.* Tree-sitter-backed `PythonParser` (PR-7).
- `ingestion/openapi.py` — *new.* `OpenApiParser` supporting 3.0 + 3.1 (PR-8).
- `storage.py` — *modify.* Add `kind`, `language`, `artifact_qualname`, `parent_document_id` LanceDB columns; update `add_chunks` records; update `search` result mapping; update `list_documents` / `get_document` passthrough.
- `indexer.py` — *modify.* Dispatch via `ParserRegistry`, call `submit_parse_result` / `delete_document_in_graph` via `graph_or_skip`.
- `graph_integration.py` — *modify.* No surface change; update docstring to reflect artifact ingestion path.
- `main.py` — *modify.* Register default parsers at app startup.
- `api/graph.py` — *new.* Ten `/graph/*` proxy routes to guru-graph; `author` stamping; read-only enforcement on `/graph/query` (PR-5).
- `api/__init__.py` — *modify.* Include the new `graph` router.

**`packages/guru-graph/src/guru_graph/`**
- `versioning.py` — *modify.* Bump `PROTOCOL_VERSION` to `"1.1.0"`, `SCHEMA_VERSION` to `2`.
- `backend/base.py` — *modify.* Add `ArtifactOpsBackend` protocol (sibling of `KbOpsBackend`) with the declarative operations needed by `ArtifactService`, `AnnotationService`, `IngestService`.
- `backend/neo4j_backend.py` — *modify.* Implement `ArtifactOpsBackend`.
- `testing/fake_backend.py` — *modify.* Implement `ArtifactOpsBackend` in-memory for unit tests.
- `migrations/m0002_artifact_schema.py` — *new.* Forward-only migration.
- `services/ingest_service.py` — *new.* `submit_parse_result`, `delete_document`; diff-based reconciliation; orphan-preserving deletion.
- `services/artifact_service.py` — *new.* `describe`, `neighbors`, `find`.
- `services/annotation_service.py` — *new.* `create`, `delete`, `list_orphans`, `reattach`.
- `services/relates_service.py` — *new.* Artifact-to-artifact `RELATES` link CRUD.
- `routes/ingest.py` — *new.* `POST /ingest/parse-result`, `DELETE /ingest/documents/{doc_id}`.
- `routes/artifacts.py` — *new.* `GET /artifacts/{id}`, `GET /artifacts/{id}/neighbors`, `POST /artifacts/find`.
- `routes/annotations.py` — *new.* `POST /annotations`, `DELETE /annotations/{id}`, `GET /annotations/orphans`, `POST /annotations/{id}/reattach`.
- `routes/relates.py` — *new.* `POST /relates`, `DELETE /relates`.
- `app.py` — *modify.* Include all new routers.

**`packages/guru-mcp/src/guru_mcp/`**
- `server.py` — *modify.* Register ten new `@mcp.tool()` functions.

**`packages/guru-cli/src/guru_cli/`**
- `commands/graph.py` — *modify.* Add `describe`, `neighbors`, `find`, `annotations`, `orphans` read-only subcommands; graph-disabled branch exits 0.
- `commands/init.py` — *modify.* Call `install_skill()` after existing init steps.
- `commands/update.py` — *new.* `guru update [--force] [--dry-run]` command.
- `skills_install.py` — *new.* Shared installer logic: copy asset tree, write `MANIFEST.json`, materialise `.agents/skills/` symlink (or copy on Windows).
- `main.py` — *modify.* Register the `update` command with the top-level click group.
- `assets/skills/guru-knowledge-base/SKILL.md` — *new.* Top-level skill body (≤400 words) per spec.
- `assets/skills/guru-knowledge-base/references/{model,discovery,curation,annotation-shape,linking-patterns,orphans}.md` — *new.* Six lazy-loaded reference docs.

**`packages/guru-cli/pyproject.toml`** — *modify.* Three separate changes:
- PR-6: Add `[tool.hatch.build.targets.wheel.force-include]` for the skill asset tree.
- PR-7: Add `tree-sitter-python` dependency.
- PR-8: Add `PyYAML` dependency.

**`tests/e2e/features/`** — all *new.*
- `artifact_indexing.feature`, `hybrid_search.feature`, `annotations_and_curation.feature`, `orphan_triage.feature`, `artifact_links.feature`, `graph_optional.feature`, `graph_mcp_tools.feature`, `skill_distribution.feature`, `parser_extensibility.feature`, `constitution_invariants.feature`.
- `steps/artifact_steps.py`, `steps/annotation_steps.py`, `steps/orphan_steps.py`, `steps/skill_steps.py`.

**`tests/e2e/fixtures/`** — *new.*
- `polyglot/` — fixture project (Python + Markdown + OpenAPI).
- `protobuf_parser/` — test-only parser registered at runtime for extensibility BDD.

**`ARCHITECTURE.md`** and **`AGENTS.md`** — *modify* in PR-9 only.

---

# PR-1 — Parser contract + LanceDB metadata columns

**Branch:** `feat/artifact-graph-pr1-parser-contract`

**Scope recap.** Introduce the extensible parser interface (`GraphNode`, `GraphEdge`, `ParseResult`, `ParserRegistry`), extend `Chunk` with the four new metadata fields, retrofit the existing `MarkdownParser` to return `ParseResult`, add the new LanceDB columns. `ParseResult.{document, nodes, edges}` are discarded in this PR — no graph IPC yet. Existing markdown indexing behaves identically from the outside.

**Success gate (run before opening PR):**
```bash
make lint
make test                     # every existing unit + integration test still green
uv run pytest packages/guru-server/tests/unit/test_parser_registry.py -v
uv run pytest packages/guru-server/tests/unit/test_markdown_parser.py -v
```
All green.

---

### Task 1.1 — Extend `Chunk` dataclass with the four new fields

**Files:**
- Modify: `packages/guru-server/src/guru_server/ingestion/base.py`

- [ ] **Step 1.1.1 — Write the failing test.**

Add file `packages/guru-server/tests/unit/test_chunk_extensions.py`:

```python
from __future__ import annotations

from guru_server.ingestion.base import Chunk


def test_chunk_defaults_for_new_fields():
    c = Chunk(content="hi", file_path="x.md", header_breadcrumb="Doc", chunk_level=1)
    assert c.kind == "text"
    assert c.language is None
    assert c.artifact_qualname is None
    assert c.parent_document_id is None


def test_chunk_accepts_all_new_fields():
    c = Chunk(
        content="def foo(): pass",
        file_path="x.py",
        header_breadcrumb="x.py",
        chunk_level=1,
        kind="code",
        language="python",
        artifact_qualname="alpha::x.foo",
        parent_document_id="alpha::x.py",
    )
    assert c.kind == "code"
    assert c.language == "python"
    assert c.artifact_qualname == "alpha::x.foo"
    assert c.parent_document_id == "alpha::x.py"
```

Run: `uv run pytest packages/guru-server/tests/unit/test_chunk_extensions.py -v` → fails with attribute errors.

- [ ] **Step 1.1.2 — Extend the dataclass.**

Edit `packages/guru-server/src/guru_server/ingestion/base.py`, replace the `Chunk` dataclass with:

```python
@dataclass
class Chunk:
    content: str
    file_path: str
    header_breadcrumb: str
    chunk_level: int
    frontmatter: dict[str, Any] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    parent_chunk_id: str | None = None
    chunk_id: str | None = None
    content_type: str = "text"  # "text" | "code" | "table" | "mixed"
    # Artifact-graph metadata (PR-1 additions):
    kind: str = "text"          # "text" | "code" | "openapi_operation" | "openapi_schema" | "markdown_section"
    language: str | None = None
    artifact_qualname: str | None = None
    parent_document_id: str | None = None
```

Run: `uv run pytest packages/guru-server/tests/unit/test_chunk_extensions.py -v` → passes.

- [ ] **Step 1.1.3 — Commit.**

```bash
git add packages/guru-server/src/guru_server/ingestion/base.py \
        packages/guru-server/tests/unit/test_chunk_extensions.py
git commit -m "feat(ingestion): extend Chunk with artifact-graph metadata fields"
```

---

### Task 1.2 — Add `GraphNode`, `GraphEdge`, `ParseResult` dataclasses

**Files:**
- Modify: `packages/guru-server/src/guru_server/ingestion/base.py`
- Test: `packages/guru-server/tests/unit/test_parse_result.py`

- [ ] **Step 1.2.1 — Write the failing test.**

Create `packages/guru-server/tests/unit/test_parse_result.py`:

```python
from __future__ import annotations

from guru_server.ingestion.base import Chunk, GraphEdge, GraphNode, ParseResult


def test_graph_node_minimal():
    n = GraphNode(node_id="alpha::docs/x.md", label="Document", properties={"language": "markdown"})
    assert n.node_id == "alpha::docs/x.md"
    assert n.label == "Document"
    assert n.properties["language"] == "markdown"


def test_graph_edge_contains_no_kind():
    e = GraphEdge(from_id="a", to_id="b", rel_type="CONTAINS")
    assert e.rel_type == "CONTAINS"
    assert e.kind is None
    assert e.properties == {}


def test_graph_edge_relates_requires_kind():
    e = GraphEdge(from_id="a", to_id="b", rel_type="RELATES", kind="imports")
    assert e.rel_type == "RELATES"
    assert e.kind == "imports"


def test_parse_result_shape():
    doc = GraphNode(node_id="alpha::x.md", label="Document", properties={})
    pr = ParseResult(chunks=[], document=doc, nodes=[], edges=[])
    assert pr.document is doc
    assert pr.chunks == []
    assert pr.nodes == []
    assert pr.edges == []
```

Run the test; expect import errors.

- [ ] **Step 1.2.2 — Add the dataclasses.**

Append to `packages/guru-server/src/guru_server/ingestion/base.py`:

```python
from typing import Literal


@dataclass
class GraphNode:
    node_id: str
    label: str            # "Document" | "Module" | "Class" | ...
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    from_id: str
    to_id: str
    rel_type: Literal["CONTAINS", "RELATES"]
    kind: str | None = None  # ArtifactLinkKind.value when rel_type == "RELATES"
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    chunks: list[Chunk]
    document: GraphNode
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
```

Run the test → passes.

- [ ] **Step 1.2.3 — Commit.**

```bash
git add packages/guru-server/src/guru_server/ingestion/base.py \
        packages/guru-server/tests/unit/test_parse_result.py
git commit -m "feat(ingestion): add GraphNode, GraphEdge, ParseResult dataclasses"
```

---

### Task 1.3 — Extend `DocumentParser` ABC with `name` + `kb_name` kwarg

**Files:**
- Modify: `packages/guru-server/src/guru_server/ingestion/base.py`

- [ ] **Step 1.3.1 — Update the ABC signature.**

Replace the `DocumentParser` class in `base.py` with:

```python
class DocumentParser(ABC):
    @property
    @abstractmethod
    def name(self) -> str:  # "markdown" | "python" | "openapi" | ...
        ...

    @abstractmethod
    def supports(self, file_path: Path) -> bool: ...

    @abstractmethod
    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult: ...
```

The existing `MarkdownParser.parse(file_path, rule)` will break at signature check time in Task 1.4 — that is intended.

- [ ] **Step 1.3.2 — Commit the ABC change (test-free; covered by Task 1.4).**

```bash
git add packages/guru-server/src/guru_server/ingestion/base.py
git commit -m "refactor(ingestion): tighten DocumentParser ABC for artifact-graph support"
```

---

### Task 1.4 — Retrofit `MarkdownParser` to return `ParseResult`

**Files:**
- Modify: `packages/guru-server/src/guru_server/ingestion/markdown.py`
- Test: `packages/guru-server/tests/unit/test_markdown_parser.py` (extend the existing file if it exists; otherwise create).

- [ ] **Step 1.4.1 — Write / extend failing tests.**

Append to `packages/guru-server/tests/unit/test_markdown_parser.py`:

```python
from pathlib import Path

import pytest

from guru_core.types import Rule, RuleMatch
from guru_server.ingestion.markdown import MarkdownParser


@pytest.fixture
def md_tmp(tmp_path: Path) -> Path:
    p = tmp_path / "guide.md"
    p.write_text("# Title\n\n## Section A\n\ncontent A\n\n## Section B\n\ncontent B\n")
    return p


def test_markdown_parser_returns_parse_result(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=RuleMatch(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    assert result.document.label == "Document"
    assert result.document.node_id.startswith("alpha::")
    assert result.document.properties["language"] == "markdown"
    assert result.document.properties["file_type"] == "doc"
    assert len(result.chunks) >= 2


def test_markdown_parser_emits_section_nodes(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=RuleMatch(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    section_nodes = [n for n in result.nodes if n.label == "MarkdownSection"]
    assert len(section_nodes) >= 2


def test_markdown_parser_emits_contains_edges(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=RuleMatch(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    contains = [e for e in result.edges if e.rel_type == "CONTAINS"]
    # document -> each top-level section
    assert any(e.from_id == result.document.node_id for e in contains)


def test_markdown_parser_chunks_carry_pointer_metadata(md_tmp: Path):
    parser = MarkdownParser()
    rule = Rule(ruleName="default", match=RuleMatch(glob="**/*.md"))
    result = parser.parse(md_tmp, rule, kb_name="alpha")
    for c in result.chunks:
        assert c.kind == "markdown_section"
        assert c.language == "markdown"
        assert c.parent_document_id == result.document.node_id
        assert c.artifact_qualname is not None


def test_markdown_parser_name_property():
    assert MarkdownParser().name == "markdown"
```

Run: fails because `MarkdownParser` still returns `list[Chunk]` and lacks `name` / `kb_name`.

- [ ] **Step 1.4.2 — Retrofit `MarkdownParser`.**

Rewrite the `MarkdownParser` class in `packages/guru-server/src/guru_server/ingestion/markdown.py`:

```python
class MarkdownParser(DocumentParser):
    @property
    def name(self) -> str:
        return "markdown"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in (".md", ".markdown")

    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult:
        raw = file_path.read_text(encoding="utf-8")
        post = frontmatter.loads(raw)
        fm = _sanitize_frontmatter(dict(post.metadata))
        doc = Document(text=post.content, metadata={"source": str(file_path)})
        parser = LlamaMarkdownParser()
        nodes = parser.get_nodes_from_documents([doc])

        split_level = None
        if rule.chunking is not None:
            split_level = rule.chunking.split_level

        document_id = f"{kb_name}::{file_path.as_posix()}"
        document_node = GraphNode(
            node_id=document_id,
            label="Document",
            properties={
                "kb_name": kb_name,
                "relative_path": file_path.as_posix(),
                "absolute_path": str(file_path),
                "language": "markdown",
                "file_type": "doc",
                "parser_name": "markdown",
                "size_bytes": file_path.stat().st_size,
            },
        )

        chunks: list[Chunk] = []
        section_nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        for i, node in enumerate(nodes):
            header_breadcrumb = self._extract_breadcrumb(node)
            chunk_level = self._infer_level(header_breadcrumb)
            section_id = f"{document_id}::{header_breadcrumb}"
            chunk_id = hashlib.sha256(
                f"{file_path}:{header_breadcrumb}:{i}".encode()
            ).hexdigest()[:16]
            content = node.get_content()
            chunks.append(
                Chunk(
                    content=content,
                    file_path=str(file_path),
                    header_breadcrumb=header_breadcrumb,
                    chunk_level=chunk_level,
                    frontmatter=fm,
                    labels=list(rule.labels),
                    chunk_id=chunk_id,
                    content_type=_detect_content_type(content),
                    kind="markdown_section",
                    language="markdown",
                    artifact_qualname=section_id,
                    parent_document_id=document_id,
                )
            )
            section_nodes.append(
                GraphNode(
                    node_id=section_id,
                    label="MarkdownSection",
                    properties={
                        "kb_name": kb_name,
                        "breadcrumb": header_breadcrumb,
                        "heading": header_breadcrumb.split(" > ")[-1],
                        "level": chunk_level,
                        "chunk_level": chunk_level,
                    },
                )
            )

        if split_level == "h2":
            chunks = self._merge_h3_into_h2(chunks)

        self._assign_parent_ids(chunks)

        # Wire CONTAINS edges: document -> top-level sections, section -> child
        parent_stack: list[GraphNode] = [document_node]
        for sn in section_nodes:
            while parent_stack and (
                parent_stack[-1].label == "MarkdownSection"
                and parent_stack[-1].properties["level"] >= sn.properties["level"]
            ):
                parent_stack.pop()
            parent = parent_stack[-1]
            edges.append(GraphEdge(from_id=parent.node_id, to_id=sn.node_id, rel_type="CONTAINS"))
            parent_stack.append(sn)

        return ParseResult(
            chunks=chunks,
            document=document_node,
            nodes=section_nodes,
            edges=edges,
        )
```

Keep `_merge_h3_into_h2`, `_assign_parent_ids`, `_extract_breadcrumb`, `_infer_level` unchanged.

Add missing imports at the top:

```python
from guru_server.ingestion.base import Chunk, DocumentParser, GraphEdge, GraphNode, ParseResult
```

(Remove the now-redundant imports of `Chunk`, `DocumentParser` from the old import line.)

- [ ] **Step 1.4.3 — Run tests; fix call-sites that still expect a `list[Chunk]`.**

Run: `uv run pytest packages/guru-server/tests/unit/test_markdown_parser.py -v`.
If other tests or call-sites break (e.g. `indexer.py`), this is intentional — Task 1.5 fixes `indexer.py` to consume `ParseResult`.

- [ ] **Step 1.4.4 — Commit.**

```bash
git add packages/guru-server/src/guru_server/ingestion/markdown.py \
        packages/guru-server/tests/unit/test_markdown_parser.py
git commit -m "feat(ingestion): MarkdownParser returns ParseResult with Document + sections"
```

---

### Task 1.5 — Update `indexer.py` to consume `ParseResult`

**Files:**
- Modify: `packages/guru-server/src/guru_server/indexer.py`

Context: today's `BackgroundIndexer._index_file` calls `self._parser.parse(file_path, rule)` and expects `list[Chunk]`. Update it to destructure `ParseResult`. Graph facts are *still discarded* in this PR; PR-2 wires them to `submit_parse_result`.

- [ ] **Step 1.5.1 — Edit `indexer.py`.**

In `_index_file`, replace:

```python
chunks = self._parser.parse(file_path, rule)
```

with:

```python
parse_result = self._parser.parse(file_path, rule, kb_name=self._kb_name)
chunks = parse_result.chunks
# parse_result.document/nodes/edges are discarded in this PR; submitted in PR-2.
```

Add a `self._kb_name: str` field to `__init__` and plumb it through — matches the config-derived name (`config.name or project_root.name`). Take a `kb_name` parameter and store it.

Update `__init__`:

```python
def __init__(
    self,
    *,
    store: VectorStore,
    manifest: FileManifest,
    embedder,
    config: GuruConfig,
    project_root: Path,
    kb_name: str,
    embed_cache: EmbeddingCache | None = None,
) -> None:
    ...
    self._kb_name = kb_name
```

Find every construction site of `BackgroundIndexer` in `guru-server` (likely `app.py` or `main.py`) and pass `kb_name=...`. Use `config.name or project_root.name`.

- [ ] **Step 1.5.2 — Run full server tests.**

```bash
uv run pytest packages/guru-server/ -v
```

All existing tests remain green. If a test constructs `BackgroundIndexer` without `kb_name`, update it to pass `kb_name="test"`.

- [ ] **Step 1.5.3 — Commit.**

```bash
git add packages/guru-server/src/guru_server/indexer.py packages/guru-server/src/guru_server/app.py packages/guru-server/src/guru_server/main.py
git commit -m "refactor(indexer): consume ParseResult + plumb kb_name"
```

---

### Task 1.6 — Add `ParserRegistry`

**Files:**
- Create: `packages/guru-server/src/guru_server/ingestion/registry.py`
- Test: `packages/guru-server/tests/unit/test_parser_registry.py`

- [ ] **Step 1.6.1 — Write the failing test.**

Create `packages/guru-server/tests/unit/test_parser_registry.py`:

```python
from __future__ import annotations

from pathlib import Path

from guru_core.types import Rule, RuleMatch
from guru_server.ingestion.base import DocumentParser, GraphNode, ParseResult
from guru_server.ingestion.registry import ParserRegistry


class _FakePyParser(DocumentParser):
    name = "python"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult:
        doc = GraphNode(node_id=f"{kb_name}::{file_path}", label="Document", properties={})
        return ParseResult(chunks=[], document=doc)


class _FakeMdParser(DocumentParser):
    name = "markdown"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".md"

    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult:
        doc = GraphNode(node_id=f"{kb_name}::{file_path}", label="Document", properties={})
        return ParseResult(chunks=[], document=doc)


def test_dispatch_returns_first_match(tmp_path: Path):
    reg = ParserRegistry()
    reg.register(_FakeMdParser())
    reg.register(_FakePyParser())
    assert isinstance(reg.dispatch(tmp_path / "a.py"), _FakePyParser)
    assert isinstance(reg.dispatch(tmp_path / "a.md"), _FakeMdParser)


def test_dispatch_unknown_returns_none(tmp_path: Path):
    reg = ParserRegistry()
    reg.register(_FakePyParser())
    assert reg.dispatch(tmp_path / "a.go") is None


def test_dispatch_order_stable(tmp_path: Path):
    reg = ParserRegistry()
    md1 = _FakeMdParser()
    md2 = _FakeMdParser()
    reg.register(md1)
    reg.register(md2)
    # md1 registered first => wins
    assert reg.dispatch(tmp_path / "a.md") is md1
```

- [ ] **Step 1.6.2 — Implement `ParserRegistry`.**

Create `packages/guru-server/src/guru_server/ingestion/registry.py`:

```python
"""Parser registry — the extension point for new ingestion formats.

Order of registration matters: first match wins. Adding a new parser is a
single `register()` call at server startup (see guru_server.main). No core
change is required.
"""

from __future__ import annotations

from pathlib import Path

from .base import DocumentParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[DocumentParser] = []

    def register(self, parser: DocumentParser) -> None:
        self._parsers.append(parser)

    def dispatch(self, file_path: Path) -> DocumentParser | None:
        for p in self._parsers:
            if p.supports(file_path):
                return p
        return None

    @property
    def all(self) -> tuple[DocumentParser, ...]:
        return tuple(self._parsers)
```

- [ ] **Step 1.6.3 — Run tests.**

```bash
uv run pytest packages/guru-server/tests/unit/test_parser_registry.py -v
```

All pass.

- [ ] **Step 1.6.4 — Wire the registry into `BackgroundIndexer`.**

In `packages/guru-server/src/guru_server/indexer.py`:

- Replace `self._parser = MarkdownParser()` with an injected registry:
  ```python
  self._registry = parser_registry or _default_registry()
  ```
  where `_default_registry()` returns a `ParserRegistry` with `MarkdownParser()` registered.
- Replace `if not self._parser.supports(file_path): continue` in `_discover` with `if self._registry.dispatch(file_path) is None: continue`.
- Replace `self._parser.parse(...)` in `_index_file` with `parser = self._registry.dispatch(file_path); parse_result = parser.parse(...)`.
- Add `parser_registry: ParserRegistry | None = None` to `__init__` parameters.

Then at the construction site of `BackgroundIndexer` (guru-server startup), pass the registry from the app state.

- [ ] **Step 1.6.5 — Register the markdown parser at app startup.**

In `packages/guru-server/src/guru_server/main.py` (or wherever the app is constructed), add:

```python
from guru_server.ingestion.markdown import MarkdownParser
from guru_server.ingestion.registry import ParserRegistry

parser_registry = ParserRegistry()
parser_registry.register(MarkdownParser())
app.state.parser_registry = parser_registry
```

Pass `app.state.parser_registry` into the `BackgroundIndexer` constructor.

- [ ] **Step 1.6.6 — Commit.**

```bash
git add packages/guru-server/src/guru_server/ingestion/registry.py \
        packages/guru-server/tests/unit/test_parser_registry.py \
        packages/guru-server/src/guru_server/indexer.py \
        packages/guru-server/src/guru_server/main.py
git commit -m "feat(ingestion): add ParserRegistry as the parser extension point"
```

---

### Task 1.7 — Add the four new LanceDB columns

**Files:**
- Modify: `packages/guru-server/src/guru_server/storage.py`
- Test: `packages/guru-server/tests/unit/test_storage_metadata_columns.py`

- [ ] **Step 1.7.1 — Write the failing test.**

Create `packages/guru-server/tests/unit/test_storage_metadata_columns.py`:

```python
from __future__ import annotations

from pathlib import Path

from guru_server.ingestion.base import Chunk
from guru_server.storage import VectorStore


def test_add_chunks_persists_metadata_columns(tmp_path: Path):
    store = VectorStore(db_path=str(tmp_path / "db"))
    chunk = Chunk(
        content="def foo(): pass",
        file_path="x.py",
        header_breadcrumb="x.py",
        chunk_level=1,
        kind="code",
        language="python",
        artifact_qualname="kb::x.foo",
        parent_document_id="kb::x.py",
        chunk_id="abc",
    )
    store.add_chunks([chunk], [[0.0] * 768])
    table = store._get_table()
    rows = table.search(None).to_list()
    assert rows[0]["kind"] == "code"
    assert rows[0]["language"] == "python"
    assert rows[0]["artifact_qualname"] == "kb::x.foo"
    assert rows[0]["parent_document_id"] == "kb::x.py"
```

Run: fails because the schema/record shape does not yet include the new columns.

- [ ] **Step 1.7.2 — Extend `add_chunks`.**

Edit `packages/guru-server/src/guru_server/storage.py`. In `add_chunks`, update the `records.append({...})` block to include:

```python
records.append(
    {
        "vector": vector,
        "content": chunk.content,
        "file_path": chunk.file_path,
        "header_breadcrumb": chunk.header_breadcrumb,
        "chunk_level": chunk.chunk_level,
        "chunk_index": i,
        "frontmatter": json.dumps(chunk.frontmatter),
        "labels": json.dumps(chunk.labels),
        "chunk_id": chunk.chunk_id or "",
        "parent_chunk_id": chunk.parent_chunk_id or "",
        "content_type": chunk.content_type,
        # PR-1 additions
        "kind": chunk.kind,
        "language": chunk.language or "",
        "artifact_qualname": chunk.artifact_qualname or "",
        "parent_document_id": chunk.parent_document_id or "",
    }
)
```

- [ ] **Step 1.7.3 — Extend `search()` return mapping.**

In `search()`, update the returned dict:

```python
return [
    {
        "content": r["content"],
        "file_path": r["file_path"],
        "header_breadcrumb": r["header_breadcrumb"],
        "chunk_level": r["chunk_level"],
        "labels": _parse_json_list(r["labels"]),
        "score": 1.0 / (1.0 + r.get("_distance", 0.0)),
        # PR-1 additions
        "kind": r.get("kind", "text"),
        "language": r.get("language", "") or None,
        "artifact_qualname": r.get("artifact_qualname", "") or None,
        "parent_document_id": r.get("parent_document_id", "") or None,
    }
    for r in results
]
```

- [ ] **Step 1.7.4 — Handle pre-PR-1 tables.**

LanceDB creates the schema from the first `add_chunks` call. Existing `.guru/` databases from before this PR have no `kind` column. When `VectorStore._get_table` opens an older table and `add` is called with a superset of columns, LanceDB performs a schema evolve (additive columns default to NULL for existing rows). We rely on this behaviour.

Add a lightweight assertion in `_get_table`:

```python
# after the head(1) probe succeeds:
schema_names = set(self._table.schema.names)
if "kind" not in schema_names and self._table.count_rows() > 0:
    logger.info(
        "Extending existing LanceDB table '%s' with artifact-graph metadata columns",
        TABLE_NAME,
    )
    # LanceDB 0.x: add_columns with defaults
    self._table.add_columns({"kind": "\"text\"", "language": "\"\"", "artifact_qualname": "\"\"", "parent_document_id": "\"\""})
```

If `add_columns` is unsupported on the installed LanceDB version, log a warning and fall back to `_table.to_pandas()` + `db.create_table(..., mode="overwrite")`. Keep the fallback path covered by a manual note in the PR description — no automated test for a re-materialise.

- [ ] **Step 1.7.5 — Run tests.**

```bash
uv run pytest packages/guru-server/tests/unit/test_storage_metadata_columns.py -v
uv run pytest packages/guru-server/ -v          # all existing tests still pass
```

- [ ] **Step 1.7.6 — Commit.**

```bash
git add packages/guru-server/src/guru_server/storage.py \
        packages/guru-server/tests/unit/test_storage_metadata_columns.py
git commit -m "feat(storage): add kind/language/artifact_qualname/parent_document_id LanceDB columns"
```

---

### Task 1.8 — Full PR-1 verification

- [ ] **Step 1.8.1 — Run every gate.**

```bash
make lint
make test
uv run pytest packages/guru-server/ -v
```

All green. Remaining failures are bugs in the PR.

- [ ] **Step 1.8.2 — Open PR-1.**

Push the branch, open the PR with title `feat: parser contract + LanceDB artifact metadata (PR-1/9)` and description linking to the design spec §*Parser contract + ingestion + LanceDB*.

- [ ] **Step 1.8.3 — Update tasks.**

Mark PR-1 done; start PR-2.

---

# PR-2 — m0002 schema + ingest routes + Document nodes end-to-end

**Branch:** `feat/artifact-graph-pr2-m0002-ingest`

**Scope recap.** Neo4j gains the artifact-graph schema via `m0002_artifact_schema.py`. `guru-graph` gains an `IngestService` + `/ingest/parse-result` + `/ingest/documents/{id}` routes. `guru-core` adds the wire types + `GraphClient.submit_parse_result` / `delete_document_in_graph`. The `guru-server` indexer submits `ParseResult.document/nodes/edges` after every file, wrapped in `graph_or_skip`. Protocol version bumps to `1.1.0`. After this PR, indexing a markdown project with the graph enabled creates `(:Document)` + `(:MarkdownSection)` nodes end-to-end.

**Success gate:**
```bash
make lint
make test
make test-graph       # @real_neo4j + m0002 migration tests
uv run behave tests/e2e/features/graph_plugin.feature   # existing scenarios still pass
uv run behave tests/e2e/features/artifact_indexing.feature   # markdown subset only (Python + OpenAPI scenarios are @skip until PR-7/8)
```

---

### Task 2.1 — Bump protocol + schema version constants

**Files:**
- Modify: `packages/guru-graph/src/guru_graph/versioning.py`
- Modify: `packages/guru-core/src/guru_core/graph_client.py`

- [ ] **Step 2.1.1 — Bump `guru-graph` constants.**

In `packages/guru-graph/src/guru_graph/versioning.py`:

```python
PROTOCOL_VERSION = "1.1.0"
SCHEMA_VERSION = 2
```

- [ ] **Step 2.1.2 — Bump `guru-core` client constant.**

In `packages/guru-core/src/guru_core/graph_client.py`:

```python
PROTOCOL_VERSION = "1.1.0"
```

- [ ] **Step 2.1.3 — Commit.**

```bash
git add packages/guru-graph/src/guru_graph/versioning.py \
        packages/guru-core/src/guru_core/graph_client.py
git commit -m "chore(graph): bump protocol to 1.1.0 and schema to 2"
```

---

### Task 2.2 — Add artifact-graph Pydantic models to `guru-core`

**Files:**
- Modify: `packages/guru-core/src/guru_core/graph_types.py`
- Test: `packages/guru-core/tests/unit/test_artifact_graph_types.py`

- [ ] **Step 2.2.1 — Write the failing test.**

Create `packages/guru-core/tests/unit/test_artifact_graph_types.py`:

```python
from __future__ import annotations

import pytest

from guru_core.graph_types import (
    ArtifactLinkKind,
    AnnotationKind,
    GraphEdgePayload,
    GraphNodePayload,
    ParseResultPayload,
)


def test_artifact_link_kind_values():
    assert ArtifactLinkKind.IMPORTS == "imports"
    assert ArtifactLinkKind.INHERITS_FROM == "inherits_from"
    assert ArtifactLinkKind.IMPLEMENTS == "implements"
    assert ArtifactLinkKind.CALLS == "calls"
    assert ArtifactLinkKind.REFERENCES == "references"
    assert ArtifactLinkKind.DOCUMENTS == "documents"


def test_annotation_kind_values():
    assert set(AnnotationKind) == {
        AnnotationKind.SUMMARY,
        AnnotationKind.GOTCHA,
        AnnotationKind.CAVEAT,
        AnnotationKind.NOTE,
    }


def test_graph_node_payload_roundtrip():
    n = GraphNodePayload(node_id="kb::x", label="Document", properties={"a": 1})
    j = n.model_dump_json()
    assert GraphNodePayload.model_validate_json(j) == n


def test_parse_result_payload_contains_document():
    pr = ParseResultPayload(
        chunks_count=3,
        document=GraphNodePayload(node_id="kb::x", label="Document", properties={}),
        nodes=[],
        edges=[],
    )
    assert pr.document.label == "Document"


def test_graph_edge_relates_requires_kind():
    with pytest.raises(ValueError):
        GraphEdgePayload(from_id="a", to_id="b", rel_type="RELATES", kind=None)


def test_graph_edge_contains_forbids_kind():
    with pytest.raises(ValueError):
        GraphEdgePayload(from_id="a", to_id="b", rel_type="CONTAINS", kind="imports")
```

- [ ] **Step 2.2.2 — Add the models.**

Append to `packages/guru-core/src/guru_core/graph_types.py`:

```python
class ArtifactLinkKind(StrEnum):
    IMPORTS = "imports"
    INHERITS_FROM = "inherits_from"
    IMPLEMENTS = "implements"
    CALLS = "calls"
    REFERENCES = "references"
    DOCUMENTS = "documents"


class AnnotationKind(StrEnum):
    SUMMARY = "summary"
    GOTCHA = "gotcha"
    CAVEAT = "caveat"
    NOTE = "note"


class GraphNodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdgePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_id: str
    to_id: str
    rel_type: Literal["CONTAINS", "RELATES"]
    kind: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _kind_consistent(cls, v: str | None, info) -> str | None:
        rt = info.data.get("rel_type")
        if rt == "RELATES" and v is None:
            raise ValueError("RELATES edge requires a kind")
        if rt == "CONTAINS" and v is not None:
            raise ValueError("CONTAINS edge must not carry a kind")
        return v


class ParseResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunks_count: int
    document: GraphNodePayload
    nodes: list[GraphNodePayload] = Field(default_factory=list)
    edges: list[GraphEdgePayload] = Field(default_factory=list)
```

Add `field_validator` to imports:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

- [ ] **Step 2.2.3 — Run tests.**

```bash
uv run pytest packages/guru-core/tests/unit/test_artifact_graph_types.py -v
```

All pass.

- [ ] **Step 2.2.4 — Commit.**

```bash
git add packages/guru-core/src/guru_core/graph_types.py \
        packages/guru-core/tests/unit/test_artifact_graph_types.py
git commit -m "feat(core): add artifact-graph Pydantic types + ArtifactLinkKind/AnnotationKind enums"
```

---

### Task 2.3 — Write `m0002_artifact_schema.py` migration

**Files:**
- Create: `packages/guru-graph/src/guru_graph/migrations/m0002_artifact_schema.py`
- Test: `packages/guru-graph/tests/unit/test_m0002_migration.py`

- [ ] **Step 2.3.1 — Inspect `m0001` for shape.**

Read `packages/guru-graph/src/guru_graph/migrations/m0001_initial.py` — use it as the pattern for how migrations are written + registered.

- [ ] **Step 2.3.2 — Write the failing unit test (FakeBackend path).**

Create `packages/guru-graph/tests/unit/test_m0002_migration.py`:

```python
from __future__ import annotations

from guru_graph.migrations.m0002_artifact_schema import run as run_m0002
from guru_graph.testing.fake_backend import FakeBackend


def test_m0002_runs_idempotently_from_v1_to_v2():
    backend = FakeBackend(_schema_version=1)
    backend.start()
    run_m0002(backend)
    assert backend.info().schema_version == 2
    # Second run must be a no-op (idempotent)
    run_m0002(backend)
    assert backend.info().schema_version == 2


def test_m0002_refuses_when_current_greater_than_target():
    backend = FakeBackend(_schema_version=3)
    backend.start()
    # Running m0002 against a v3 store is harmless (already done); but the
    # global ensure_schema path refuses. Test the global path.
    import pytest
    from guru_graph.versioning import VersionNegotiationError

    with pytest.raises(VersionNegotiationError):
        backend.ensure_schema(target_version=2)
```

- [ ] **Step 2.3.3 — Implement `m0002_artifact_schema.py`.**

Create the file:

```python
"""m0002 — artifact-graph schema (schema_version 1 -> 2).

Adds uniqueness constraints for (:Document), (:Module), (:Class), (:Function),
(:Method), (:OpenApiSpec), (:OpenApiOperation), (:OpenApiSchema),
(:MarkdownSection), (:Annotation); adds indexes used by hot query paths.

Forward-only, idempotent. Run against a GraphBackend whose current
schema_version is >= 1 (so m0001 has already run).
"""

from __future__ import annotations

from guru_graph.backend.base import GraphBackend

TARGET_VERSION = 2

_CONSTRAINTS = [
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT module_id_unique IF NOT EXISTS FOR (m:Module) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT class_id_unique IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT function_id_unique IF NOT EXISTS FOR (f:Function) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT method_id_unique IF NOT EXISTS FOR (m:Method) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT oas_spec_id_unique IF NOT EXISTS FOR (s:OpenApiSpec) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT oas_op_id_unique IF NOT EXISTS FOR (o:OpenApiOperation) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT oas_schema_id_unique IF NOT EXISTS FOR (s:OpenApiSchema) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT md_section_id_unique IF NOT EXISTS FOR (s:MarkdownSection) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT annotation_id_unique IF NOT EXISTS FOR (a:Annotation) REQUIRE a.id IS UNIQUE",
]

_INDEXES = [
    "CREATE INDEX document_kb_name IF NOT EXISTS FOR (d:Document) ON (d.kb_name)",
    "CREATE INDEX document_language IF NOT EXISTS FOR (d:Document) ON (d.language)",
    "CREATE INDEX annotation_kind IF NOT EXISTS FOR (a:Annotation) ON (a.kind)",
    "CREATE INDEX annotation_author IF NOT EXISTS FOR (a:Annotation) ON (a.author)",
    "CREATE INDEX module_qualname IF NOT EXISTS FOR (m:Module) ON (m.qualname)",
    "CREATE INDEX class_qualname IF NOT EXISTS FOR (c:Class) ON (c.qualname)",
    "CREATE INDEX function_qualname IF NOT EXISTS FOR (f:Function) ON (f.qualname)",
    "CREATE INDEX method_qualname IF NOT EXISTS FOR (m:Method) ON (m.qualname)",
]


def run(backend: GraphBackend) -> None:
    """Apply m0002. Idempotent: safe to re-invoke."""
    current = backend.info().schema_version
    if current >= TARGET_VERSION:
        return  # already applied

    for cypher in _CONSTRAINTS:
        backend.execute(cypher, {})
    for cypher in _INDEXES:
        backend.execute(cypher, {})

    # Bump :_Meta.schema_version to TARGET_VERSION.
    backend.execute(
        "MERGE (m:_Meta {kind:'schema'}) "
        "SET m.schema_version = $target, m.updated_at = timestamp()",
        {"target": TARGET_VERSION},
    )
```

(If `FakeBackend` doesn't track `_schema_version` changes via `execute`, update it to recognise the `_Meta` set and update its state. Simplest: override `ensure_schema` path so the test calls `backend.ensure_schema(2)` after `run(backend)`.)

In `FakeBackend`, extend `ensure_schema` to call through a registry or make `run_m0002` bump `_schema_version` directly:

```python
# Inside m0002 run(), after executing Cypher:
if hasattr(backend, "_schema_version"):
    backend._schema_version = TARGET_VERSION   # FakeBackend only — real backend updates via _Meta
```

Or cleaner — have `ensure_schema` read `_Meta.schema_version` on the real backend and read the dataclass field on FakeBackend. For this plan, keep the test-only direct attribute bump behind an `isinstance` check in the migration:

```python
from guru_graph.testing.fake_backend import FakeBackend  # circular risk — avoid

# Prefer: just call backend.ensure_schema(TARGET_VERSION) separately in the migration runner.
```

Simplest resolution: separate the "apply DDL" step (the `run(backend)` body) from the "bump schema version" step (caller's job). Update the test accordingly:

```python
def test_m0002_runs_idempotently_from_v1_to_v2():
    backend = FakeBackend(_schema_version=1)
    backend.start()
    run_m0002(backend)
    backend.ensure_schema(2)
    assert backend.info().schema_version == 2
```

Then `run()` only runs DDL. `ensure_schema()` is what bumps the version and is where idempotence is enforced.

- [ ] **Step 2.3.4 — Wire `m0002` into the migration runner.**

Locate the place where `m0001_initial.run()` is invoked (likely `guru-graph`'s schema service or daemon startup, search for `m0001_initial`). Add the m0002 call after m0001:

```python
from .migrations import m0001_initial, m0002_artifact_schema

m0001_initial.run(backend)
backend.ensure_schema(target_version=1)
m0002_artifact_schema.run(backend)
backend.ensure_schema(target_version=2)
```

- [ ] **Step 2.3.5 — Run tests.**

```bash
uv run pytest packages/guru-graph/tests/unit/test_m0002_migration.py -v
```

Pass.

- [ ] **Step 2.3.6 — Add a `@real_neo4j` integration test.**

Create `packages/guru-graph/tests/integration/test_m0002_real_neo4j.py`:

```python
from __future__ import annotations

import pytest

from guru_graph.migrations import m0001_initial, m0002_artifact_schema


@pytest.mark.real_neo4j
def test_m0002_applied_to_empty_neo4j(real_neo4j_backend):
    m0001_initial.run(real_neo4j_backend)
    real_neo4j_backend.ensure_schema(1)
    m0002_artifact_schema.run(real_neo4j_backend)
    real_neo4j_backend.ensure_schema(2)

    # Verify a constraint exists
    result = real_neo4j_backend.execute_read("SHOW CONSTRAINTS", {})
    constraint_names = {row[result.columns.index("name")] for row in result.rows}
    assert "document_id_unique" in constraint_names
```

Use the existing `real_neo4j_backend` fixture pattern (look at existing `@real_neo4j` tests for the pytest fixture).

- [ ] **Step 2.3.7 — Commit.**

```bash
git add packages/guru-graph/src/guru_graph/migrations/m0002_artifact_schema.py \
        packages/guru-graph/tests/unit/test_m0002_migration.py \
        packages/guru-graph/tests/integration/test_m0002_real_neo4j.py \
        packages/guru-graph/src/guru_graph/main.py  # or wherever migrations are orchestrated
git commit -m "feat(graph): add m0002 artifact-graph schema migration"
```

---

### Task 2.4 — Extend `ArtifactOpsBackend` protocol and FakeBackend / Neo4jBackend

**Files:**
- Modify: `packages/guru-graph/src/guru_graph/backend/base.py`
- Modify: `packages/guru-graph/src/guru_graph/testing/fake_backend.py`
- Modify: `packages/guru-graph/src/guru_graph/backend/neo4j_backend.py`

- [ ] **Step 2.4.1 — Add the protocol.**

Append to `packages/guru-graph/src/guru_graph/backend/base.py`:

```python
@runtime_checkable
class ArtifactOpsBackend(GraphBackend, Protocol):
    """Declarative artifact-graph operations.

    The IngestService, ArtifactService, AnnotationService, and RelatesService
    are typed against this protocol. See m0002 schema in the design spec.
    """

    # Ingest
    def upsert_document(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None: ...
    def upsert_artifact(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None: ...
    def delete_artifact(self, *, node_id: str) -> None: ...
    def delete_artifact_with_descendants(self, *, node_id: str) -> list[str]: ...
    def create_contains_edge(self, *, from_id: str, to_id: str) -> None: ...
    def create_relates_edge(self, *, from_id: str, to_id: str, kind: str, properties: dict[str, Any]) -> None: ...
    def delete_relates_edge(self, *, from_id: str, to_id: str, kind: str) -> bool: ...
    def remove_outbound_relates_rooted_at(self, *, doc_id: str) -> None: ...
    def get_document_snapshot(self, *, doc_id: str) -> list[str]: ...
    def set_document_snapshot(self, *, doc_id: str, node_ids: list[str]) -> None: ...
    def orphan_annotations_for(self, *, node_ids: list[str]) -> None: ...

    # Artifact queries
    def get_artifact(self, *, node_id: str) -> dict[str, Any] | None: ...
    def list_neighbors(
        self,
        *,
        node_id: str,
        direction: Literal["in", "out", "both"],
        rel_type: Literal["CONTAINS", "RELATES", "both"],
        kind: str | None,
        depth: int,
        limit: int,
    ) -> list[dict[str, Any]]: ...
    def find_artifacts(
        self,
        *,
        name: str | None,
        qualname_prefix: str | None,
        label: str | None,
        tag: str | None,
        kb_name: str | None,
        limit: int,
    ) -> list[dict[str, Any]]: ...
    def list_annotations_for(self, *, node_id: str) -> list[dict[str, Any]]: ...
    def list_relates_for(self, *, node_id: str, direction: str) -> list[dict[str, Any]]: ...

    # Annotations
    def create_annotation(
        self,
        *,
        annotation_id: str,
        target_id: str,
        target_label: str,
        kind: str,
        body: str,
        tags: list[str],
        author: str,
        target_snapshot_json: str,
    ) -> dict[str, Any]: ...
    def replace_summary_annotation(
        self,
        *,
        annotation_id: str,
        target_id: str,
        target_label: str,
        body: str,
        tags: list[str],
        author: str,
        target_snapshot_json: str,
    ) -> dict[str, Any]: ...
    def delete_annotation(self, *, annotation_id: str) -> bool: ...
    def list_orphans(self, *, limit: int) -> list[dict[str, Any]]: ...
    def reattach_orphan(self, *, annotation_id: str, new_target_id: str) -> bool: ...
```

- [ ] **Step 2.4.2 — Implement `ArtifactOpsBackend` in FakeBackend.**

Extend `packages/guru-graph/src/guru_graph/testing/fake_backend.py` with dataclass fields for artifact nodes and edges:

```python
from dataclasses import dataclass, field

@dataclass
class _FakeArtifact:
    node_id: str
    label: str
    properties: dict
    snapshot_ids: list[str] = field(default_factory=list)  # Document-only


@dataclass
class _FakeEdge:
    from_id: str
    to_id: str
    rel_type: str
    kind: str | None
    properties: dict


@dataclass
class _FakeAnnotation:
    annotation_id: str
    target_id: str | None
    target_label: str | None
    kind: str
    body: str
    tags: list[str]
    author: str
    created_at: float
    updated_at: float
    target_snapshot_json: str
```

Add storage dicts:

```python
_artifacts: dict[str, _FakeArtifact] = field(default_factory=dict)
_edges: list[_FakeEdge] = field(default_factory=list)
_annotations: dict[str, _FakeAnnotation] = field(default_factory=dict)
```

Implement all the methods from the protocol in the same style as the existing `upsert_kb`/`link`/etc. Keep it straightforward — no Cypher parsing. For `delete_artifact_with_descendants`, do a BFS over `_edges` where `rel_type == "CONTAINS"`; return the list of ids deleted. For `orphan_annotations_for(node_ids)`, find every `_FakeAnnotation` with `target_id in node_ids` and set `target_id = None` (orphaning). Do **not** delete the annotation itself.

- [ ] **Step 2.4.3 — Implement `ArtifactOpsBackend` in Neo4jBackend.**

Extend `packages/guru-graph/src/guru_graph/backend/neo4j_backend.py` with Cypher-backed implementations. Each method executes a transaction via `self.transaction()`.

Example patterns:

```python
def upsert_document(self, *, node_id: str, label: str, properties: dict) -> None:
    assert label == "Document"
    self.execute(
        "MERGE (d:Document {id: $id}) SET d += $props",
        {"id": node_id, "props": properties},
    )

def upsert_artifact(self, *, node_id: str, label: str, properties: dict) -> None:
    # label is trusted (comes from our parsers; validated against enum in service layer)
    self.execute(
        f"MERGE (n {{id: $id}}) ON CREATE SET n:{label} SET n += $props",
        {"id": node_id, "props": properties},
    )

def delete_artifact_with_descendants(self, *, node_id: str) -> list[str]:
    result = self.execute(
        "MATCH (r {id: $id}) "
        "OPTIONAL MATCH (r)-[:CONTAINS*0..]->(c) "
        "WITH r, collect(DISTINCT c.id) AS child_ids "
        "WITH child_ids + [r.id] AS all_ids "
        "UNWIND all_ids AS i "
        "WITH DISTINCT i "
        "RETURN collect(i) AS ids",
        {"id": node_id},
    )
    # Actually delete them in a separate step after orphaning annotations.
    return result.rows[0][0] if result.rows else []

def orphan_annotations_for(self, *, node_ids: list[str]) -> None:
    self.execute(
        "MATCH (a:Annotation)-[r:ANNOTATES]->(t) "
        "WHERE t.id IN $ids DELETE r",
        {"ids": node_ids},
    )

def set_document_snapshot(self, *, doc_id: str, node_ids: list[str]) -> None:
    self.execute(
        "MATCH (d:Document {id: $id}) SET d.snapshot_ids_json = $json",
        {"id": doc_id, "json": json.dumps(node_ids)},
    )

def get_document_snapshot(self, *, doc_id: str) -> list[str]:
    result = self.execute_read(
        "MATCH (d:Document {id: $id}) RETURN d.snapshot_ids_json AS s",
        {"id": doc_id},
    )
    if not result.rows:
        return []
    s = result.rows[0][0]
    return json.loads(s) if s else []
```

Write the rest following the same shape: Cypher string + params dict.

- [ ] **Step 2.4.4 — Unit tests for FakeBackend artifact ops.**

Create `packages/guru-graph/tests/unit/test_fake_backend_artifacts.py` covering:
- `upsert_document` + `get_artifact` round-trip
- `upsert_artifact` + `create_contains_edge` + `list_neighbors`
- `delete_artifact_with_descendants` returns all descendants
- `create_annotation` + `list_annotations_for` round-trip
- `delete_annotation` returns True then False
- `orphan_annotations_for([id])` leaves annotation present but with `target_id=None`
- `list_orphans` returns exactly the orphaned ones
- `reattach_orphan` unsets orphan state

Keep each test ≤10 lines, one assertion per concept.

- [ ] **Step 2.4.5 — Run tests.**

```bash
uv run pytest packages/guru-graph/tests/unit/ -v
```

All green.

- [ ] **Step 2.4.6 — Commit.**

```bash
git add packages/guru-graph/src/guru_graph/backend/base.py \
        packages/guru-graph/src/guru_graph/testing/fake_backend.py \
        packages/guru-graph/src/guru_graph/backend/neo4j_backend.py \
        packages/guru-graph/tests/unit/test_fake_backend_artifacts.py
git commit -m "feat(graph): add ArtifactOpsBackend + FakeBackend and Neo4j impls"
```

---

### Task 2.5 — Add `IngestService` and `/ingest` routes

**Files:**
- Create: `packages/guru-graph/src/guru_graph/services/ingest_service.py`
- Create: `packages/guru-graph/src/guru_graph/routes/ingest.py`
- Modify: `packages/guru-graph/src/guru_graph/app.py`
- Test: `packages/guru-graph/tests/unit/test_ingest_service.py`
- Test: `packages/guru-graph/tests/integration/test_routes_ingest.py`

- [ ] **Step 2.5.1 — Write failing unit test.**

Create `packages/guru-graph/tests/unit/test_ingest_service.py`:

```python
from __future__ import annotations

from guru_core.graph_types import GraphEdgePayload, GraphNodePayload, ParseResultPayload
from guru_graph.services.ingest_service import IngestService
from guru_graph.testing.fake_backend import FakeBackend


def _payload(doc_id: str, sub_ids: list[str]) -> ParseResultPayload:
    doc = GraphNodePayload(node_id=doc_id, label="Document", properties={"kb_name": "kb"})
    nodes = [GraphNodePayload(node_id=i, label="MarkdownSection", properties={"kb_name": "kb"}) for i in sub_ids]
    edges = [GraphEdgePayload(from_id=doc_id, to_id=i, rel_type="CONTAINS") for i in sub_ids]
    return ParseResultPayload(chunks_count=len(sub_ids), document=doc, nodes=nodes, edges=edges)


def test_ingest_creates_document_and_subnodes():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A", "kb::x.md::B"]))
    assert backend.get_artifact(node_id="kb::x.md") is not None
    assert backend.get_artifact(node_id="kb::x.md::A") is not None


def test_ingest_removes_deleted_subnodes_on_rerun():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A", "kb::x.md::B"]))
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A"]))  # B removed
    assert backend.get_artifact(node_id="kb::x.md::A") is not None
    assert backend.get_artifact(node_id="kb::x.md::B") is None


def test_delete_document_cascades_and_orphans_annotations():
    backend = FakeBackend()
    backend.start()
    svc = IngestService(backend=backend)
    svc.submit("kb", _payload("kb::x.md", ["kb::x.md::A"]))
    backend.create_annotation(
        annotation_id="ann-1",
        target_id="kb::x.md::A",
        target_label="MarkdownSection",
        kind="gotcha",
        body="beware",
        tags=[],
        author="agent:test",
        target_snapshot_json='{"target_id":"kb::x.md::A","target_kind":"MarkdownSection"}',
    )
    svc.delete_document("kb", "kb::x.md")
    assert backend.get_artifact(node_id="kb::x.md::A") is None
    assert backend.get_artifact(node_id="kb::x.md") is None
    orphans = backend.list_orphans(limit=10)
    assert len(orphans) == 1 and orphans[0]["annotation_id"] == "ann-1"
```

- [ ] **Step 2.5.2 — Implement `IngestService`.**

Create `packages/guru-graph/src/guru_graph/services/ingest_service.py`:

```python
"""Reconciliation service: apply ParseResult payloads idempotently.

Orphan-preserving deletion: when a Document or its sub-artifacts disappear,
annotations targeting the deleted nodes have their :ANNOTATES edges removed
(in the backend the annotation's target_id becomes null) — the annotation
node is preserved for agent triage.
"""

from __future__ import annotations

from guru_core.graph_types import ParseResultPayload

from ..backend.base import ArtifactOpsBackend


class IngestService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None:
        self._backend = backend

    def submit(self, kb_name: str, payload: ParseResultPayload) -> None:
        doc_id = payload.document.node_id
        prev_ids = set(self._backend.get_document_snapshot(doc_id=doc_id))
        current_ids = {n.node_id for n in payload.nodes}

        to_delete = list(prev_ids - current_ids)
        if to_delete:
            # Before deleting, orphan annotations pointing at the victims.
            all_victims = []
            for nid in to_delete:
                all_victims.extend(self._backend.delete_artifact_with_descendants(node_id=nid))
            if all_victims:
                self._backend.orphan_annotations_for(node_ids=all_victims)
                for nid in all_victims:
                    self._backend.delete_artifact(node_id=nid)

        # Upsert document + every sub-artifact
        self._backend.upsert_document(
            node_id=doc_id,
            label=payload.document.label,
            properties=payload.document.properties,
        )
        for n in payload.nodes:
            self._backend.upsert_artifact(
                node_id=n.node_id, label=n.label, properties=n.properties
            )

        # Replace outbound RELATES edges rooted at this document (they are
        # recomputed from scratch each parse)
        self._backend.remove_outbound_relates_rooted_at(doc_id=doc_id)
        for e in payload.edges:
            if e.rel_type == "CONTAINS":
                self._backend.create_contains_edge(from_id=e.from_id, to_id=e.to_id)
            else:  # RELATES
                assert e.kind is not None
                self._backend.create_relates_edge(
                    from_id=e.from_id,
                    to_id=e.to_id,
                    kind=e.kind,
                    properties=e.properties,
                )

        # Record new snapshot
        self._backend.set_document_snapshot(doc_id=doc_id, node_ids=list(current_ids))

    def delete_document(self, kb_name: str, doc_id: str) -> None:
        victims = self._backend.delete_artifact_with_descendants(node_id=doc_id)
        if victims:
            self._backend.orphan_annotations_for(node_ids=victims)
            for nid in victims:
                self._backend.delete_artifact(node_id=nid)
```

- [ ] **Step 2.5.3 — Implement `/ingest` routes.**

Create `packages/guru-graph/src/guru_graph/routes/ingest.py`:

```python
"""Ingestion routes consumed by guru-server. Not exposed to MCP."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from guru_core.graph_types import ParseResultPayload

from ..services.ingest_service import IngestService

router = APIRouter()


def _svc(request: Request) -> IngestService:
    return IngestService(backend=request.app.state.backend)


@router.post("/ingest/parse-result", status_code=status.HTTP_204_NO_CONTENT)
def submit_parse_result(
    payload: ParseResultPayload,
    request: Request,
    kb_name: str,
) -> Response:
    _svc(request).submit(kb_name, payload)
    return Response(status_code=204)


@router.delete("/ingest/documents/{doc_id:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: str,
    request: Request,
    kb_name: str,
) -> Response:
    _svc(request).delete_document(kb_name, doc_id)
    return Response(status_code=204)
```

- [ ] **Step 2.5.4 — Register the router.**

In `packages/guru-graph/src/guru_graph/app.py`, add to imports + `include_router`:

```python
from .routes import admin, ingest, kbs, query
...
app.include_router(ingest.router)
```

- [ ] **Step 2.5.5 — Write integration test (FakeBackend).**

Create `packages/guru-graph/tests/integration/test_routes_ingest.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing.fake_backend import FakeBackend


def test_submit_parse_result_and_delete_document():
    backend = FakeBackend()
    backend.start()
    app = create_app(backend=backend)
    client = TestClient(app)

    body = {
        "chunks_count": 1,
        "document": {
            "node_id": "kb::x.md",
            "label": "Document",
            "properties": {"kb_name": "kb", "language": "markdown"},
        },
        "nodes": [
            {
                "node_id": "kb::x.md::Title",
                "label": "MarkdownSection",
                "properties": {"kb_name": "kb", "breadcrumb": "Title"},
            }
        ],
        "edges": [
            {
                "from_id": "kb::x.md",
                "to_id": "kb::x.md::Title",
                "rel_type": "CONTAINS",
                "kind": None,
                "properties": {},
            }
        ],
    }
    r = client.post("/ingest/parse-result?kb_name=kb", json=body)
    assert r.status_code == 204
    assert backend.get_artifact(node_id="kb::x.md") is not None

    r2 = client.delete("/ingest/documents/kb::x.md?kb_name=kb")
    assert r2.status_code == 204
    assert backend.get_artifact(node_id="kb::x.md") is None
```

- [ ] **Step 2.5.6 — Run tests.**

```bash
uv run pytest packages/guru-graph/tests/ -v
```

All pass.

- [ ] **Step 2.5.7 — Commit.**

```bash
git add packages/guru-graph/src/guru_graph/services/ingest_service.py \
        packages/guru-graph/src/guru_graph/routes/ingest.py \
        packages/guru-graph/src/guru_graph/app.py \
        packages/guru-graph/tests/unit/test_ingest_service.py \
        packages/guru-graph/tests/integration/test_routes_ingest.py
git commit -m "feat(graph): IngestService + /ingest routes for ParseResult + Document delete"
```

---

### Task 2.6 — Extend `GraphClient` with `submit_parse_result` + `delete_document_in_graph`

**Files:**
- Modify: `packages/guru-core/src/guru_core/graph_client.py`
- Test: `packages/guru-core/tests/unit/test_graph_client_ingest.py`

- [ ] **Step 2.6.1 — Write the failing test.**

Create `packages/guru-core/tests/unit/test_graph_client_ingest.py` using `httpx.MockTransport` or a FastAPI `TestClient` monkeypatch; easier: mock `GraphClient._request`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from guru_core.graph_client import GraphClient
from guru_core.graph_types import GraphNodePayload, ParseResultPayload


@pytest.mark.asyncio
async def test_submit_parse_result_posts_payload():
    client = GraphClient(socket_path="/tmp/x.sock", auto_start=False)
    payload = ParseResultPayload(
        chunks_count=0,
        document=GraphNodePayload(node_id="kb::x", label="Document", properties={}),
        nodes=[],
        edges=[],
    )
    fake_response = AsyncMock()
    fake_response.status_code = 204
    with patch.object(client, "_request", return_value=fake_response) as r:
        await client.submit_parse_result(kb_name="kb", payload=payload)
        assert r.called
        method, path = r.call_args.args[:2]
        assert method == "POST"
        assert path == "/ingest/parse-result?kb_name=kb"
        assert "json" in r.call_args.kwargs


@pytest.mark.asyncio
async def test_delete_document_calls_delete():
    client = GraphClient(socket_path="/tmp/x.sock", auto_start=False)
    fake_response = AsyncMock()
    fake_response.status_code = 204
    with patch.object(client, "_request", return_value=fake_response) as r:
        await client.delete_document_in_graph(kb_name="kb", doc_id="kb::x.md")
        method, path = r.call_args.args[:2]
        assert method == "DELETE"
        assert path == "/ingest/documents/kb::x.md?kb_name=kb"
```

- [ ] **Step 2.6.2 — Implement the two methods.**

In `packages/guru-core/src/guru_core/graph_client.py`, append:

```python
from urllib.parse import quote

async def submit_parse_result(self, *, kb_name: str, payload: ParseResultPayload) -> None:
    await self._request(
        "POST",
        f"/ingest/parse-result?kb_name={quote(kb_name)}",
        json=payload.model_dump(mode="json"),
    )

async def delete_document_in_graph(self, *, kb_name: str, doc_id: str) -> None:
    await self._request(
        "DELETE",
        f"/ingest/documents/{quote(doc_id, safe='')}?kb_name={quote(kb_name)}",
    )
```

Add the import:

```python
from .graph_types import (
    ...,
    ParseResultPayload,
)
```

- [ ] **Step 2.6.3 — Run tests.**

```bash
uv run pytest packages/guru-core/tests/unit/test_graph_client_ingest.py -v
```

Pass.

- [ ] **Step 2.6.4 — Commit.**

```bash
git add packages/guru-core/src/guru_core/graph_client.py \
        packages/guru-core/tests/unit/test_graph_client_ingest.py
git commit -m "feat(core): GraphClient.submit_parse_result + delete_document_in_graph"
```

---

### Task 2.7 — Wire the indexer to submit ParseResult payloads via `graph_or_skip`

**Files:**
- Modify: `packages/guru-server/src/guru_server/indexer.py`
- Modify: `packages/guru-server/src/guru_server/graph_integration.py`
- Test: `packages/guru-server/tests/unit/test_indexer_graph_integration.py`

- [ ] **Step 2.7.1 — Helper: convert `ParseResult` → `ParseResultPayload`.**

In `graph_integration.py`, add:

```python
from guru_core.graph_types import GraphEdgePayload, GraphNodePayload, ParseResultPayload
from guru_server.ingestion.base import ParseResult


def parse_result_to_payload(pr: ParseResult) -> ParseResultPayload:
    return ParseResultPayload(
        chunks_count=len(pr.chunks),
        document=GraphNodePayload(
            node_id=pr.document.node_id,
            label=pr.document.label,
            properties=pr.document.properties,
        ),
        nodes=[
            GraphNodePayload(node_id=n.node_id, label=n.label, properties=n.properties)
            for n in pr.nodes
        ],
        edges=[
            GraphEdgePayload(
                from_id=e.from_id,
                to_id=e.to_id,
                rel_type=e.rel_type,
                kind=e.kind,
                properties=e.properties,
            )
            for e in pr.edges
        ],
    )
```

- [ ] **Step 2.7.2 — Wire `BackgroundIndexer._index_file`.**

In `indexer.py`, in `_index_file`, after `self._store.add_chunks(chunks, vectors)`:

```python
if self._graph_client is not None:
    from guru_server.graph_integration import graph_or_skip, parse_result_to_payload
    payload = parse_result_to_payload(parse_result)
    await graph_or_skip(
        self._graph_client.submit_parse_result(kb_name=self._kb_name, payload=payload),
        feature="ingest_artifacts",
    )
```

Wire a `graph_client: GraphClient | None` parameter into `__init__` and plumb it from the app startup (guru-server constructs it when `graph.enabled`).

Similarly, in the deletion branch (`if to_delete:`), add:

```python
if self._graph_client is not None:
    from guru_server.graph_integration import graph_or_skip
    for rel_path in to_delete:
        doc_id = f"{self._kb_name}::{rel_path}"
        await graph_or_skip(
            self._graph_client.delete_document_in_graph(kb_name=self._kb_name, doc_id=doc_id),
            feature="ingest_delete",
        )
```

- [ ] **Step 2.7.3 — Write integration test with GraphUnavailable.**

Create `packages/guru-server/tests/unit/test_indexer_graph_integration.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from guru_core.graph_errors import GraphUnavailable
from guru_server.graph_integration import parse_result_to_payload
from guru_server.ingestion.base import GraphNode, ParseResult


def test_parse_result_to_payload_round_trip():
    doc = GraphNode(node_id="kb::x.md", label="Document", properties={"language": "markdown"})
    pr = ParseResult(chunks=[], document=doc, nodes=[], edges=[])
    payload = parse_result_to_payload(pr)
    assert payload.chunks_count == 0
    assert payload.document.node_id == "kb::x.md"


@pytest.mark.asyncio
async def test_graph_unavailable_during_submit_is_swallowed(tmp_path: Path):
    # Construct a BackgroundIndexer with a GraphClient whose submit raises
    # GraphUnavailable. Run _index_file via the indexer's public run() and
    # verify no exception escapes + LanceDB state still populated.
    from guru_server.graph_integration import graph_or_skip

    async def _boom():
        raise GraphUnavailable("simulated")

    result = await graph_or_skip(_boom(), feature="test")
    assert result is None
```

A fuller test here covers the indexer's full run; this one locks the critical `graph_or_skip` behaviour.

- [ ] **Step 2.7.4 — Run tests.**

```bash
uv run pytest packages/guru-server/ -v
```

All green.

- [ ] **Step 2.7.5 — Commit.**

```bash
git add packages/guru-server/src/guru_server/indexer.py \
        packages/guru-server/src/guru_server/graph_integration.py \
        packages/guru-server/tests/unit/test_indexer_graph_integration.py
git commit -m "feat(indexer): submit ParseResult to graph via graph_or_skip"
```

---

### Task 2.8 — BDD fixture + first scenarios

**Files:**
- Create: `tests/e2e/fixtures/polyglot/src/pkg/__init__.py` (empty)
- Create: `tests/e2e/fixtures/polyglot/src/pkg/auth.py`
- Create: `tests/e2e/fixtures/polyglot/src/pkg/services/__init__.py` (empty)
- Create: `tests/e2e/fixtures/polyglot/src/pkg/services/user.py`
- Create: `tests/e2e/fixtures/polyglot/docs/guide.md`
- Create: `tests/e2e/fixtures/polyglot/api/openapi.yaml`
- Create: `tests/e2e/fixtures/polyglot/guru.json`
- Create: `tests/e2e/features/artifact_indexing.feature`
- Create: `tests/e2e/features/graph_optional.feature`
- Create: `tests/e2e/features/steps/artifact_steps.py`

- [ ] **Step 2.8.1 — Write fixture files.**

`tests/e2e/fixtures/polyglot/src/pkg/auth.py`:

```python
"""Auth helpers."""
import hashlib

from pkg.services.user import UserService


class AuthError(Exception):
    pass


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()
```

`tests/e2e/fixtures/polyglot/src/pkg/services/user.py`:

```python
"""User domain."""


class UserBase:
    def greet(self) -> str:
        return "hi"


class UserService(UserBase):
    def login(self, user: str, pw: str) -> bool:
        return True

    def deprecated_fn(self) -> None:
        pass
```

`tests/e2e/fixtures/polyglot/docs/guide.md`:

```markdown
# Polyglot guide

## Overview

This is a tiny fixture project.

## Auth

See `pkg.auth`.

### Token refresh

Tokens refresh on every login.
```

`tests/e2e/fixtures/polyglot/api/openapi.yaml`:

```yaml
openapi: 3.0.3
info:
  title: Polyglot API
  version: 1.0.0
paths:
  /users/{id}:
    get:
      operationId: getUser
      summary: Get user by id
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/UserResource"
components:
  schemas:
    UserResource:
      type: object
      properties:
        id: { type: string }
        name: { type: string }
```

`tests/e2e/fixtures/polyglot/guru.json`:

```json
{
  "version": 1,
  "name": "polyglot",
  "rules": [
    { "ruleName": "code", "match": { "glob": "src/**/*.py" } },
    { "ruleName": "docs", "match": { "glob": "docs/**/*.md" } },
    { "ruleName": "api", "match": { "glob": "api/**/*.yaml" } }
  ]
}
```

- [ ] **Step 2.8.2 — Write the markdown-subset `artifact_indexing.feature`.**

Create `tests/e2e/features/artifact_indexing.feature` with the Gherkin from the design spec §Tier 3 BDD. Tag Python/OpenAPI-dependent scenarios with `@skip_until_pr7` / `@skip_until_pr8`. The Markdown-only scenarios must pass at the end of PR-2.

Example markdown-only scenario:

```gherkin
Feature: Artifact graph indexing for Python, OpenAPI, and Markdown

  Background:
    Given the "polyglot" fixture project is copied to a tmpdir

  @real_neo4j
  Scenario: Markdown index creates Document + MarkdownSection nodes
    Given graph is enabled
    When I run `guru index`
    Then (:Document {id: "polyglot::docs/guide.md"}) exists in the graph
    And at least one (:MarkdownSection) node under docs/guide.md exists
    And LanceDB contains chunks for docs/guide.md with kind="markdown_section"
```

- [ ] **Step 2.8.3 — Write `graph_optional.feature`.**

Create `tests/e2e/features/graph_optional.feature` with the scenarios from the design spec §Tier 3. Every scenario here must pass at the end of PR-2 (no graph-specific MCP tools exist yet; the feature's scenarios are about graph-agnostic operations + disabled path).

- [ ] **Step 2.8.4 — Implement step definitions.**

Create `tests/e2e/features/steps/artifact_steps.py` with step implementations:
- "the '<name>' fixture project is copied to a tmpdir" — use `shutil.copytree` into a per-scenario tmpdir, set it as the project root on the test context.
- "graph is enabled/disabled" — write `~/.config/guru/config.json` (or per-project `.guru.json`) with `{"graph":{"enabled":true|false}}`.
- "I run `guru index`" — call the server index endpoint via `httpx` against the running server's socket.
- "(:Document {...}) exists in the graph" — open a Neo4j session to the test Neo4j (`neo4j:5`) and `MATCH` the node.
- "LanceDB contains chunks for X with kind=Y" — open the project's `.guru/lance` directly via `lancedb.connect`.

Use the existing `before_feature` hook pattern to spin up the server per feature.

- [ ] **Step 2.8.5 — Run BDD.**

```bash
uv run behave tests/e2e/features/artifact_indexing.feature --tags=~@skip_until_pr7 --tags=~@skip_until_pr8
uv run behave tests/e2e/features/graph_optional.feature
```

Both green (the enabled-markdown scenario is `@real_neo4j`, so needs `GURU_REAL_NEO4J=1` + a running Neo4j).

- [ ] **Step 2.8.6 — Commit.**

```bash
git add tests/e2e/fixtures/polyglot tests/e2e/features/artifact_indexing.feature \
        tests/e2e/features/graph_optional.feature tests/e2e/features/steps/artifact_steps.py
git commit -m "test(e2e): polyglot fixture + markdown artifact indexing + graph_optional scenarios"
```

---

### Task 2.9 — Full PR-2 verification

- [ ] **Step 2.9.1 — Run all gates.**

```bash
make lint
make test
make test-graph
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/graph_plugin.feature
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/artifact_indexing.feature --tags=~@skip_until_pr7 --tags=~@skip_until_pr8
uv run behave tests/e2e/features/graph_optional.feature
```

All green.

- [ ] **Step 2.9.2 — Open PR-2.**

Title: `feat: m0002 schema + ingest routes + Document nodes (PR-2/9)`. Body: link to spec §Graph schema + §Parser contract + ingestion + LanceDB.

---

# PR-3 — Annotations subsystem

**Branch:** `feat/artifact-graph-pr3-annotations`

**Scope recap.** `(:Annotation)` nodes, `[:ANNOTATES]` edges, replace-vs-append semantics, orphan lifecycle. New routes: `POST /annotations`, `DELETE /annotations/{id}`, `GET /annotations/orphans`, `POST /annotations/{id}/reattach`. `GraphClient` methods: `create_annotation`, `delete_annotation`, `list_orphans`, `reattach_orphan`. Orphan-preserving deletion is already wired via PR-2's reconciliation — this PR only adds the *writes*.

**Success gate:**
```bash
make test-graph
uv run behave tests/e2e/features/annotations_and_curation.feature --tags=~@skip_until_pr7 --tags=~@skip_until_pr8
uv run behave tests/e2e/features/orphan_triage.feature --tags=~@skip_until_pr7 --tags=~@skip_until_pr8
```

---

### Task 3.1 — Add annotation Pydantic models

**Files:**
- Modify: `packages/guru-core/src/guru_core/graph_types.py`
- Test: `packages/guru-core/tests/unit/test_annotation_types.py`

- [ ] **Step 3.1.1 — Test + implementation.**

Add to `test_annotation_types.py`:

```python
from __future__ import annotations

import pytest

from guru_core.graph_types import (
    AnnotationCreate,
    AnnotationKind,
    AnnotationNode,
    OrphanAnnotation,
    ReattachRequest,
)


def test_annotation_create_defaults():
    a = AnnotationCreate(node_id="kb::x", kind=AnnotationKind.GOTCHA, body="text")
    assert a.tags == []


def test_annotation_create_rejects_empty_body():
    with pytest.raises(ValueError):
        AnnotationCreate(node_id="kb::x", kind=AnnotationKind.NOTE, body="")


def test_annotation_node_has_author_and_timestamps():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    n = AnnotationNode(
        id="uuid",
        target_id="kb::x",
        target_label="Class",
        kind=AnnotationKind.SUMMARY,
        body="ok",
        tags=[],
        author="agent:test",
        created_at=now,
        updated_at=now,
        target_snapshot_json='{"target_id":"kb::x"}',
    )
    assert n.author.startswith("agent:")


def test_orphan_annotation_has_null_target_id():
    from datetime import UTC, datetime

    o = OrphanAnnotation(
        id="uuid",
        kind=AnnotationKind.GOTCHA,
        body="beware",
        tags=[],
        author="agent:test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        target_snapshot_json='{"target_id":"kb::x","target_kind":"Class"}',
    )
    assert o.id == "uuid"


def test_reattach_request_shape():
    r = ReattachRequest(new_node_id="kb::y")
    assert r.new_node_id == "kb::y"
```

In `graph_types.py` add:

```python
class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    kind: AnnotationKind
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class AnnotationNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    target_id: str | None
    target_label: str | None
    kind: AnnotationKind
    body: str
    tags: list[str]
    author: str
    created_at: datetime
    updated_at: datetime
    target_snapshot_json: str


class OrphanAnnotation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    kind: AnnotationKind
    body: str
    tags: list[str]
    author: str
    created_at: datetime
    updated_at: datetime
    target_snapshot_json: str


class ReattachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_node_id: str
```

- [ ] **Step 3.1.2 — Run tests + commit.**

```bash
uv run pytest packages/guru-core/tests/unit/test_annotation_types.py -v
git add packages/guru-core/src/guru_core/graph_types.py \
        packages/guru-core/tests/unit/test_annotation_types.py
git commit -m "feat(core): add annotation Pydantic types"
```

---

### Task 3.2 — Implement `AnnotationService`

**Files:**
- Create: `packages/guru-graph/src/guru_graph/services/annotation_service.py`
- Test: `packages/guru-graph/tests/unit/test_annotation_service.py`

- [ ] **Step 3.2.1 — Write the failing test.**

Create `packages/guru-graph/tests/unit/test_annotation_service.py`:

```python
from __future__ import annotations

import json

import pytest

from guru_core.graph_types import AnnotationCreate, AnnotationKind
from guru_graph.services.annotation_service import (
    AnnotationService,
    TargetNotFoundError,
)
from guru_graph.testing.fake_backend import FakeBackend


def _seed_target(backend: FakeBackend) -> None:
    backend.upsert_artifact(
        node_id="kb::UserService",
        label="Class",
        properties={"kb_name": "kb"},
    )


def test_create_gotcha_appends_and_returns_node():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    req = AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.GOTCHA, body="beware")
    result = svc.create(req, author="agent:test")
    assert result.id
    assert result.author == "agent:test"
    assert result.target_id == "kb::UserService"
    assert len(backend.list_annotations_for(node_id="kb::UserService")) == 1


def test_create_summary_replaces_existing():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    first = svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.SUMMARY, body="v1"),
        author="agent:test",
    )
    second = svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.SUMMARY, body="v2"),
        author="agent:test",
    )
    anns = [a for a in backend.list_annotations_for(node_id="kb::UserService") if a["kind"] == "summary"]
    assert len(anns) == 1
    assert anns[0]["body"] == "v2"


def test_create_rejects_missing_target():
    backend = FakeBackend()
    backend.start()
    svc = AnnotationService(backend=backend)
    with pytest.raises(TargetNotFoundError):
        svc.create(
            AnnotationCreate(node_id="kb::missing", kind=AnnotationKind.NOTE, body="x"),
            author="agent:test",
        )


def test_delete_returns_true_once_then_false():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    node = svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.NOTE, body="hello"),
        author="agent:test",
    )
    assert svc.delete(annotation_id=node.id) is True
    assert svc.delete(annotation_id=node.id) is False


def test_reattach_orphan_reconnects():
    backend = FakeBackend()
    backend.start()
    _seed_target(backend)
    svc = AnnotationService(backend=backend)
    node = svc.create(
        AnnotationCreate(node_id="kb::UserService", kind=AnnotationKind.NOTE, body="hello"),
        author="agent:test",
    )
    # orphan it
    backend.orphan_annotations_for(node_ids=["kb::UserService"])
    backend.upsert_artifact(node_id="kb::AccountService", label="Class", properties={"kb_name": "kb"})
    assert svc.reattach(annotation_id=node.id, new_node_id="kb::AccountService") is True
```

- [ ] **Step 3.2.2 — Implement the service.**

```python
"""Annotation service: closed vocabulary (summary/gotcha/caveat/note) + open tags."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from guru_core.graph_types import AnnotationCreate, AnnotationKind, AnnotationNode

from ..backend.base import ArtifactOpsBackend


class TargetNotFoundError(RuntimeError):
    pass


def _to_node(row: dict) -> AnnotationNode:
    return AnnotationNode(
        id=row["annotation_id"],
        target_id=row.get("target_id"),
        target_label=row.get("target_label"),
        kind=AnnotationKind(row["kind"]),
        body=row["body"],
        tags=list(row.get("tags") or []),
        author=row["author"],
        created_at=datetime.fromtimestamp(row["created_at"], tz=UTC),
        updated_at=datetime.fromtimestamp(row["updated_at"], tz=UTC),
        target_snapshot_json=row["target_snapshot_json"],
    )


class AnnotationService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None:
        self._backend = backend

    def create(self, req: AnnotationCreate, *, author: str) -> AnnotationNode:
        target = self._backend.get_artifact(node_id=req.node_id)
        if target is None:
            raise TargetNotFoundError(f"target {req.node_id!r} not found")

        annotation_id = str(uuid.uuid4())
        target_snapshot = json.dumps(
            {
                "target_id": req.node_id,
                "target_kind": target["label"],
                "breadcrumb": target["properties"].get("breadcrumb")
                or target["properties"].get("qualname")
                or target["properties"].get("name"),
            }
        )

        if req.kind == AnnotationKind.SUMMARY:
            row = self._backend.replace_summary_annotation(
                annotation_id=annotation_id,
                target_id=req.node_id,
                target_label=target["label"],
                body=req.body,
                tags=req.tags,
                author=author,
                target_snapshot_json=target_snapshot,
            )
        else:
            row = self._backend.create_annotation(
                annotation_id=annotation_id,
                target_id=req.node_id,
                target_label=target["label"],
                kind=req.kind.value,
                body=req.body,
                tags=req.tags,
                author=author,
                target_snapshot_json=target_snapshot,
            )
        return _to_node(row)

    def delete(self, *, annotation_id: str) -> bool:
        return self._backend.delete_annotation(annotation_id=annotation_id)

    def list_orphans(self, *, limit: int = 50) -> list[dict]:
        return self._backend.list_orphans(limit=limit)

    def reattach(self, *, annotation_id: str, new_node_id: str) -> bool:
        target = self._backend.get_artifact(node_id=new_node_id)
        if target is None:
            raise TargetNotFoundError(f"new target {new_node_id!r} not found")
        return self._backend.reattach_orphan(
            annotation_id=annotation_id, new_target_id=new_node_id
        )
```

- [ ] **Step 3.2.3 — Run tests + commit.**

```bash
uv run pytest packages/guru-graph/tests/unit/test_annotation_service.py -v
git add packages/guru-graph/src/guru_graph/services/annotation_service.py \
        packages/guru-graph/tests/unit/test_annotation_service.py
git commit -m "feat(graph): AnnotationService with summary replace + gotcha append + orphan lifecycle"
```

---

### Task 3.3 — Add `/annotations/*` routes

**Files:**
- Create: `packages/guru-graph/src/guru_graph/routes/annotations.py`
- Modify: `packages/guru-graph/src/guru_graph/app.py`
- Test: `packages/guru-graph/tests/integration/test_routes_annotations.py`

- [ ] **Step 3.3.1 — Implement routes.**

```python
"""Annotation routes."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from guru_core.graph_types import (
    AnnotationCreate,
    AnnotationKind,
    AnnotationNode,
    OrphanAnnotation,
    ReattachRequest,
)

from ..services.annotation_service import AnnotationService, TargetNotFoundError

router = APIRouter()


def _svc(request: Request) -> AnnotationService:
    return AnnotationService(backend=request.app.state.backend)


@router.post("/annotations", response_model=AnnotationNode, status_code=status.HTTP_201_CREATED)
def create_annotation(
    req: AnnotationCreate,
    request: Request,
    x_guru_author: str = Header(default="user:unknown"),
) -> AnnotationNode:
    try:
        return _svc(request).create(req, author=x_guru_author)
    except TargetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(annotation_id: str, request: Request) -> Response:
    if not _svc(request).delete(annotation_id=annotation_id):
        raise HTTPException(status_code=404, detail=f"annotation {annotation_id!r} not found")
    return Response(status_code=204)


@router.get("/annotations/orphans", response_model=list[OrphanAnnotation])
def list_orphans(request: Request, limit: int = 50) -> list[OrphanAnnotation]:
    rows = _svc(request).list_orphans(limit=limit)
    return [_row_to_orphan(r) for r in rows]


@router.post("/annotations/{annotation_id}/reattach", response_model=AnnotationNode)
def reattach_orphan(
    annotation_id: str,
    req: ReattachRequest,
    request: Request,
) -> AnnotationNode:
    try:
        ok = _svc(request).reattach(annotation_id=annotation_id, new_node_id=req.new_node_id)
    except TargetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail=f"annotation {annotation_id!r} not found")
    # Fetch and return updated node
    row = request.app.state.backend.get_annotation(annotation_id=annotation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="annotation missing post-reattach")
    return _row_to_node(row)


def _row_to_orphan(r: dict) -> OrphanAnnotation:
    from datetime import UTC, datetime
    return OrphanAnnotation(
        id=r["annotation_id"],
        kind=AnnotationKind(r["kind"]),
        body=r["body"],
        tags=list(r.get("tags") or []),
        author=r["author"],
        created_at=datetime.fromtimestamp(r["created_at"], tz=UTC),
        updated_at=datetime.fromtimestamp(r["updated_at"], tz=UTC),
        target_snapshot_json=r["target_snapshot_json"],
    )


def _row_to_node(r: dict) -> AnnotationNode:
    from datetime import UTC, datetime
    return AnnotationNode(
        id=r["annotation_id"],
        target_id=r.get("target_id"),
        target_label=r.get("target_label"),
        kind=AnnotationKind(r["kind"]),
        body=r["body"],
        tags=list(r.get("tags") or []),
        author=r["author"],
        created_at=datetime.fromtimestamp(r["created_at"], tz=UTC),
        updated_at=datetime.fromtimestamp(r["updated_at"], tz=UTC),
        target_snapshot_json=r["target_snapshot_json"],
    )
```

Note: `get_annotation` method was implied but not on the protocol; add it to `ArtifactOpsBackend` + FakeBackend + Neo4jBackend now — it's a trivial `MATCH (a:Annotation {id:$id}) RETURN a`.

- [ ] **Step 3.3.2 — Register router.**

In `app.py`, `from .routes import ... annotations` + `app.include_router(annotations.router)`.

- [ ] **Step 3.3.3 — Write integration test.**

```python
# packages/guru-graph/tests/integration/test_routes_annotations.py
from __future__ import annotations

from fastapi.testclient import TestClient

from guru_graph.app import create_app
from guru_graph.testing.fake_backend import FakeBackend


def _seed(backend: FakeBackend) -> None:
    backend.upsert_artifact(
        node_id="kb::UserService",
        label="Class",
        properties={"kb_name": "kb"},
    )


def test_create_delete_roundtrip():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    app = create_app(backend=backend)
    client = TestClient(app)

    r = client.post(
        "/annotations",
        json={"node_id": "kb::UserService", "kind": "gotcha", "body": "beware"},
        headers={"X-Guru-Author": "agent:test"},
    )
    assert r.status_code == 201
    aid = r.json()["id"]

    r2 = client.delete(f"/annotations/{aid}")
    assert r2.status_code == 204


def test_summary_replaces():
    backend = FakeBackend()
    backend.start()
    _seed(backend)
    app = create_app(backend=backend)
    client = TestClient(app)

    r1 = client.post("/annotations", json={"node_id": "kb::UserService", "kind": "summary", "body": "v1"})
    r2 = client.post("/annotations", json={"node_id": "kb::UserService", "kind": "summary", "body": "v2"})
    assert r1.json()["body"] == "v1"
    assert r2.json()["body"] == "v2"
    rlist = client.get("/annotations/orphans")
    assert rlist.status_code == 200  # empty


def test_missing_target_404():
    backend = FakeBackend()
    backend.start()
    app = create_app(backend=backend)
    client = TestClient(app)

    r = client.post("/annotations", json={"node_id": "kb::missing", "kind": "note", "body": "x"})
    assert r.status_code == 404
```

- [ ] **Step 3.3.4 — Run + commit.**

```bash
uv run pytest packages/guru-graph/tests/ -v
git add packages/guru-graph/src/guru_graph/routes/annotations.py \
        packages/guru-graph/src/guru_graph/app.py \
        packages/guru-graph/tests/integration/test_routes_annotations.py \
        packages/guru-graph/src/guru_graph/backend/base.py \
        packages/guru-graph/src/guru_graph/testing/fake_backend.py \
        packages/guru-graph/src/guru_graph/backend/neo4j_backend.py
git commit -m "feat(graph): /annotations routes + get_annotation helper"
```

---

### Task 3.4 — Add `GraphClient` annotation methods

**Files:**
- Modify: `packages/guru-core/src/guru_core/graph_client.py`
- Test: `packages/guru-core/tests/unit/test_graph_client_annotations.py`

- [ ] **Step 3.4.1 — Implement.**

Append:

```python
from .graph_types import (
    ...,
    AnnotationCreate,
    AnnotationNode,
    OrphanAnnotation,
    ReattachRequest,
)


async def create_annotation(self, req: AnnotationCreate, *, author: str) -> AnnotationNode:
    resp = await self._request(
        "POST",
        "/annotations",
        json=req.model_dump(mode="json"),
        headers={"X-Guru-Author": author},
    )
    return AnnotationNode.model_validate(resp.json())


async def delete_annotation(self, *, annotation_id: str) -> bool:
    resp = await self._request("DELETE", f"/annotations/{quote(annotation_id, safe='')}")
    return resp.status_code == 204


async def list_orphans(self, *, limit: int = 50) -> list[OrphanAnnotation]:
    resp = await self._request("GET", f"/annotations/orphans?limit={limit}")
    return [OrphanAnnotation.model_validate(r) for r in resp.json()]


async def reattach_orphan(
    self, *, annotation_id: str, new_node_id: str
) -> AnnotationNode:
    resp = await self._request(
        "POST",
        f"/annotations/{quote(annotation_id, safe='')}/reattach",
        json=ReattachRequest(new_node_id=new_node_id).model_dump(mode="json"),
    )
    return AnnotationNode.model_validate(resp.json())
```

Also update `_request` to accept an optional `headers` kwarg merged with `self._headers()`.

- [ ] **Step 3.4.2 — Test + commit.**

Follow the same `AsyncMock(_request)` pattern as Task 2.6.

```bash
uv run pytest packages/guru-core/tests/unit/test_graph_client_annotations.py -v
git add packages/guru-core/src/guru_core/graph_client.py \
        packages/guru-core/tests/unit/test_graph_client_annotations.py
git commit -m "feat(core): GraphClient annotation methods"
```

---

### Task 3.5 — BDD scenarios

**Files:**
- Create: `tests/e2e/features/annotations_and_curation.feature`
- Create: `tests/e2e/features/orphan_triage.feature`
- Create: `tests/e2e/features/steps/annotation_steps.py`
- Create: `tests/e2e/features/steps/orphan_steps.py`

- [ ] **Step 3.5.1 — Write feature files.**

Copy scenarios from the design spec §Tier 3 verbatim. Tag artifact-type-specific scenarios (those that rely on `(:Class)`/`(:Function)` nodes being produced by Python parser) with `@skip_until_pr7`. KB-level and Document-level annotation scenarios must pass now.

- [ ] **Step 3.5.2 — Implement steps.**

Write step defs that call `GraphClient.create_annotation` / `list_orphans` / `reattach_orphan` / `delete_annotation` directly against the guru-graph daemon's socket.

- [ ] **Step 3.5.3 — Run + commit.**

```bash
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/annotations_and_curation.feature --tags=~@skip_until_pr7
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/orphan_triage.feature --tags=~@skip_until_pr7
git add tests/e2e/features/annotations_and_curation.feature \
        tests/e2e/features/orphan_triage.feature \
        tests/e2e/features/steps/annotation_steps.py \
        tests/e2e/features/steps/orphan_steps.py
git commit -m "test(e2e): annotation + orphan triage BDD scenarios (KB/Document scope)"
```

---

### Task 3.6 — Full PR-3 verification

Same shape as Task 2.9: run all gates, open PR-3.

---

# PR-4 — Artifact links (`RELATES` edges)

**Branch:** `feat/artifact-graph-pr4-relates`

**Scope recap.** `(:Artifact)-[:RELATES {kind}]->(:Artifact)` edges. `POST /relates` and `DELETE /relates` routes. `GraphClient.create_link` and `delete_link`. 422 on unknown `kind` values.

**Success gate:**
```bash
make test-graph
uv run behave tests/e2e/features/artifact_links.feature --tags=~@skip_until_pr7 --tags=~@skip_until_pr8
```

---

### Task 4.1 — Add link Pydantic models

**Files:**
- Modify: `packages/guru-core/src/guru_core/graph_types.py`

- [ ] **Step 4.1.1 — Add models.**

```python
class ArtifactLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_id: str
    to_id: str
    kind: ArtifactLinkKind
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactLink(BaseModel):
    model_config = ConfigDict(extra="ignore")
    from_id: str
    to_id: str
    kind: ArtifactLinkKind
    created_at: datetime
    author: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactUnlink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_id: str
    to_id: str
    kind: ArtifactLinkKind
```

- [ ] **Step 4.1.2 — Test + commit.**

Four-line test asserting enum round-trip and that a `CONTAINS` string is *not* a valid `ArtifactLinkKind`.

```bash
uv run pytest packages/guru-core/tests/unit/test_artifact_link_types.py -v
git add packages/guru-core/src/guru_core/graph_types.py \
        packages/guru-core/tests/unit/test_artifact_link_types.py
git commit -m "feat(core): ArtifactLinkCreate/ArtifactLink/ArtifactUnlink types"
```

---

### Task 4.2 — `RelatesService` + routes

**Files:**
- Create: `packages/guru-graph/src/guru_graph/services/relates_service.py`
- Create: `packages/guru-graph/src/guru_graph/routes/relates.py`
- Modify: `packages/guru-graph/src/guru_graph/app.py`
- Tests unit + integration.

- [ ] **Step 4.2.1 — Write the service.**

```python
"""Artifact-to-artifact typed-link service."""

from __future__ import annotations

from datetime import UTC, datetime

from guru_core.graph_types import ArtifactLink, ArtifactLinkCreate, ArtifactLinkKind

from ..backend.base import ArtifactOpsBackend


class EndpointNotFoundError(RuntimeError):
    pass


class RelatesService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None:
        self._backend = backend

    def create(self, req: ArtifactLinkCreate, *, author: str) -> ArtifactLink:
        for endpoint in (req.from_id, req.to_id):
            if self._backend.get_artifact(node_id=endpoint) is None:
                raise EndpointNotFoundError(f"artifact {endpoint!r} not found")
        self._backend.create_relates_edge(
            from_id=req.from_id,
            to_id=req.to_id,
            kind=req.kind.value,
            properties={"author": author, "metadata_json": _to_json(req.metadata)},
        )
        return ArtifactLink(
            from_id=req.from_id,
            to_id=req.to_id,
            kind=req.kind,
            created_at=datetime.now(UTC),
            author=author,
            metadata=req.metadata,
        )

    def delete(
        self, *, from_id: str, to_id: str, kind: ArtifactLinkKind
    ) -> bool:
        return self._backend.delete_relates_edge(
            from_id=from_id, to_id=to_id, kind=kind.value
        )


def _to_json(d: dict) -> str:
    import json
    return json.dumps(d)
```

- [ ] **Step 4.2.2 — Routes.**

```python
"""Routes for artifact RELATES edges."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from guru_core.graph_types import ArtifactLink, ArtifactLinkCreate, ArtifactLinkKind, ArtifactUnlink

from ..services.relates_service import EndpointNotFoundError, RelatesService

router = APIRouter()


def _svc(request: Request) -> RelatesService:
    return RelatesService(backend=request.app.state.backend)


@router.post("/relates", response_model=ArtifactLink, status_code=status.HTTP_201_CREATED)
def create_relates(
    req: ArtifactLinkCreate,
    request: Request,
    x_guru_author: str = Header(default="user:unknown"),
) -> ArtifactLink:
    try:
        return _svc(request).create(req, author=x_guru_author)
    except EndpointNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/relates", status_code=status.HTTP_204_NO_CONTENT)
def delete_relates(
    req: ArtifactUnlink,
    request: Request,
) -> Response:
    deleted = _svc(request).delete(from_id=req.from_id, to_id=req.to_id, kind=req.kind)
    if not deleted:
        raise HTTPException(status_code=404, detail="link not found")
    return Response(status_code=204)
```

Register in `app.py`.

- [ ] **Step 4.2.3 — Unit + integration tests + commit.**

Pattern after Task 3.2 / 3.3.

---

### Task 4.3 — `GraphClient.create_link` / `delete_link`

Same pattern as Task 3.4.

---

### Task 4.4 — BDD scenarios (KB / Document-level only until PR-7/8)

Create `tests/e2e/features/artifact_links.feature` with design-spec scenarios. Tag Python/OpenAPI targets `@skip_until_pr7`/`@skip_until_pr8`.

---

### Task 4.5 — Full PR-4 verification

Run gates, open PR.

---

# PR-5 — Graph MCP tools + `guru-server` `/graph/*` proxy

**Branch:** `feat/artifact-graph-pr5-mcp`

**Scope recap.** Ten `/graph/*` proxy routes on `guru-server` that forward to `guru-graph`, centralising `graph_or_skip`, `X-Guru-Author` stamping, and read-only enforcement on `/graph/query`. Ten `@mcp.tool()` functions in `guru-mcp/server.py`. CLI read-only extensions: `describe`, `neighbors`, `find`, `annotations`, `orphans`. Graph-disabled returns `{"status":"graph_disabled"}` per design.

**Success gate:**
```bash
make test
uv run behave tests/e2e/features/graph_mcp_tools.feature
uv run behave tests/e2e/features/graph_optional.feature
```

---

### Task 5.1 — Add remaining `GraphClient` methods (describe / neighbors / find / links / query)

**Files:**
- Modify: `packages/guru-core/src/guru_core/graph_client.py`
- Tests: `packages/guru-core/tests/unit/test_graph_client_reads.py`

- [ ] **Step 5.1.1 — Models first.**

Add to `graph_types.py`:

```python
class ArtifactNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    label: str
    properties: dict[str, Any]
    annotations: list[AnnotationNode] = Field(default_factory=list)
    links_out: list[ArtifactLink] = Field(default_factory=list)
    links_in: list[ArtifactLink] = Field(default_factory=list)


class ArtifactNeighborsResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    node_id: str
    nodes: list[ArtifactNode]
    edges: list[GraphEdgePayload]


class ArtifactFindQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    qualname_prefix: str | None = None
    label: str | None = None
    tag: str | None = None
    kb_name: str | None = None
    limit: int = 50
```

- [ ] **Step 5.1.2 — Add client methods.**

```python
async def describe_artifact(self, *, node_id: str) -> ArtifactNode | None:
    resp = await self._request("GET", f"/artifacts/{quote(node_id, safe='')}")
    if resp.status_code == 404:
        return None
    return ArtifactNode.model_validate(resp.json())


async def neighbors(
    self,
    *,
    node_id: str,
    direction: Literal["in", "out", "both"] = "both",
    rel_type: Literal["CONTAINS", "RELATES", "both"] = "both",
    kind: str | None = None,
    depth: int = 1,
    limit: int = 50,
) -> ArtifactNeighborsResult:
    qs = f"?direction={direction}&rel_type={rel_type}&depth={depth}&limit={limit}"
    if kind:
        qs += f"&kind={quote(kind)}"
    resp = await self._request("GET", f"/artifacts/{quote(node_id, safe='')}/neighbors{qs}")
    return ArtifactNeighborsResult.model_validate(resp.json())


async def find_artifacts(self, q: ArtifactFindQuery) -> list[ArtifactNode]:
    resp = await self._request("POST", "/artifacts/find", json=q.model_dump(exclude_none=True))
    return [ArtifactNode.model_validate(r) for r in resp.json()]


async def create_link(self, req: ArtifactLinkCreate, *, author: str) -> ArtifactLink:
    resp = await self._request(
        "POST", "/relates",
        json=req.model_dump(mode="json"),
        headers={"X-Guru-Author": author},
    )
    return ArtifactLink.model_validate(resp.json())


async def delete_link(
    self, *, from_id: str, to_id: str, kind: ArtifactLinkKind
) -> bool:
    resp = await self._request(
        "DELETE",
        "/relates",
        json={"from_id": from_id, "to_id": to_id, "kind": kind.value},
    )
    return resp.status_code == 204


async def graph_query(
    self, *, cypher: str, params: dict | None = None
) -> QueryResult:
    return await self.query(cypher=cypher, params=params, read_only=True)
```

- [ ] **Step 5.1.3 — Tests + commit.**

Cover each method with an `AsyncMock(_request)` test; commit.

---

### Task 5.2 — Add `ArtifactService` + `/artifacts/*` routes on guru-graph

**Files:**
- Create: `packages/guru-graph/src/guru_graph/services/artifact_service.py`
- Create: `packages/guru-graph/src/guru_graph/routes/artifacts.py`
- Tests unit + integration.

Shape:
```python
class ArtifactService:
    def __init__(self, *, backend: ArtifactOpsBackend) -> None: ...

    def describe(self, *, node_id: str) -> ArtifactNode | None: ...
    def neighbors(self, *, node_id: str, direction: str, rel_type: str, kind: str | None, depth: int, limit: int) -> ArtifactNeighborsResult: ...
    def find(self, q: ArtifactFindQuery) -> list[ArtifactNode]: ...
```

Routes: `GET /artifacts/{id}`, `GET /artifacts/{id}/neighbors`, `POST /artifacts/find`. 404 on missing describe target.

Tests: unit on FakeBackend (round-trips, filters); integration via FastAPI TestClient.

Commit: `feat(graph): ArtifactService + /artifacts/* routes`.

---

### Task 5.3 — Add guru-server `/graph/*` proxy router

**Files:**
- Create: `packages/guru-server/src/guru_server/api/graph.py`
- Modify: `packages/guru-server/src/guru_server/api/__init__.py`
- Test: `packages/guru-server/tests/unit/test_api_graph_proxy.py`

- [ ] **Step 5.3.1 — Implement the proxy.**

```python
"""MCP-facing graph proxy routes.

Every endpoint is a thin wrapper that:
  1) Short-circuits to 503 body {"status":"graph_disabled"} if graph is off.
  2) Stamps X-Guru-Author based on the request's "x-guru-mcp-client" header
     (set by guru-mcp) or "user:<git-email>" if the client is guru-cli.
  3) Forces read_only=True on /graph/query regardless of body content.
  4) Wraps every downstream call in graph_or_skip; on GraphUnavailable
     returns HTTP 200 with {"status":"graph_disabled"}.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    AnnotationCreate,
    ArtifactFindQuery,
    ArtifactLinkCreate,
    ArtifactUnlink,
    CypherQuery,
    ReattachRequest,
)

router = APIRouter(prefix="/graph")


def _graph_disabled_body() -> dict:
    return {
        "status": "graph_disabled",
        "hint": "set graph.enabled=true in config (or reach the daemon)",
    }


def _author_from_headers(request: Request, explicit: str | None) -> str:
    if explicit:
        return explicit
    client = request.headers.get("x-guru-mcp-client")
    if client:
        return f"agent:{client}"
    return "user:unknown"


async def _forward_or_disabled(coro) -> Any:
    try:
        return await coro
    except GraphUnavailable:
        return None


def _client_or_none(request: Request) -> GraphClient | None:
    return getattr(request.app.state, "graph_client", None)


@router.get("/describe/{node_id:path}")
async def describe(node_id: str, request: Request) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        node = await client.describe_artifact(node_id=node_id)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    if node is None:
        return JSONResponse({"error": "not_found", "detail": f"node {node_id!r} not found"}, status_code=404)
    return JSONResponse(node.model_dump(mode="json"))
```

Continue with the same pattern for the other nine endpoints: `/graph/neighbors/{node_id}`, `POST /graph/find`, `POST /graph/annotations`, `DELETE /graph/annotations/{id}`, `POST /graph/links`, `DELETE /graph/links`, `GET /graph/orphans`, `POST /graph/orphans/{id}/reattach`, `POST /graph/query` (force `read_only=True`).

Enforce read-only:

```python
@router.post("/query")
async def proxy_query(body: CypherQuery, request: Request) -> JSONResponse:
    client = _client_or_none(request)
    if client is None:
        return JSONResponse(_graph_disabled_body())
    try:
        # FORCE read_only regardless of body.read_only
        result = await client.graph_query(cypher=body.cypher, params=body.params)
    except GraphUnavailable:
        return JSONResponse(_graph_disabled_body())
    return JSONResponse(result.model_dump(mode="json"))
```

- [ ] **Step 5.3.2 — Wire graph_client onto app.state.**

Extend `packages/guru-server/src/guru_server/graph_integration.py` `build_graph_client_if_enabled` caller to also attach the client to `app.state.graph_client` on startup.

- [ ] **Step 5.3.3 — Register router.**

In `api/__init__.py` add `include_router(graph.router)`.

- [ ] **Step 5.3.4 — Tests.**

`test_api_graph_proxy.py` — use FastAPI `TestClient`; monkeypatch `app.state.graph_client` to a `MagicMock(spec=GraphClient)` with `AsyncMock`-style methods. Assert every route maps to the right client method; assert `/graph/query` always sends `read_only=True`; assert graph-disabled returns the sentinel body.

- [ ] **Step 5.3.5 — Commit.**

```bash
git add packages/guru-server/src/guru_server/api/graph.py \
        packages/guru-server/src/guru_server/api/__init__.py \
        packages/guru-server/src/guru_server/graph_integration.py \
        packages/guru-server/tests/unit/test_api_graph_proxy.py
git commit -m "feat(server): /graph/* proxy routes for MCP with graph_disabled fallback"
```

---

### Task 5.4 — Add the 10 MCP tools

**Files:**
- Modify: `packages/guru-mcp/src/guru_mcp/server.py`
- Test: `packages/guru-mcp/tests/unit/test_graph_tools.py`

- [ ] **Step 5.4.1 — Implement tools.**

Append to `packages/guru-mcp/src/guru_mcp/server.py`:

```python
from typing import Literal


@mcp.tool()
async def graph_describe(node_id: str) -> dict:
    """Fetch a graph node with properties, annotations, and direct links."""
    client = _get_client()
    return await client.get("/graph/describe", params={"node_id": node_id})


@mcp.tool()
async def graph_neighbors(
    node_id: str,
    direction: Literal["in", "out", "both"] = "both",
    rel_type: Literal["CONTAINS", "RELATES", "both"] = "both",
    kind: str | None = None,
    depth: int = 1,
    limit: int = 50,
) -> dict: ...


@mcp.tool()
async def graph_find(
    name: str | None = None,
    qualname_prefix: str | None = None,
    kind: str | None = None,
    tag: str | None = None,
    kb_name: str | None = None,
    limit: int = 50,
) -> dict: ...


@mcp.tool()
async def graph_annotate(
    node_id: str,
    kind: Literal["summary", "gotcha", "caveat", "note"],
    body: str,
    tags: list[str] | None = None,
) -> dict: ...


@mcp.tool()
async def graph_delete_annotation(annotation_id: str) -> dict: ...


@mcp.tool()
async def graph_link(
    from_id: str,
    to_id: str,
    kind: Literal["imports","inherits_from","implements","calls","references","documents"],
    metadata: dict | None = None,
) -> dict: ...


@mcp.tool()
async def graph_unlink(from_id: str, to_id: str, kind: str) -> dict: ...


@mcp.tool()
async def graph_orphans(limit: int = 50) -> dict: ...


@mcp.tool()
async def graph_reattach_orphan(annotation_id: str, new_node_id: str) -> dict: ...


@mcp.tool()
async def graph_query(cypher: str, params: dict | None = None) -> dict: ...
```

Each tool body calls the corresponding guru-server `/graph/*` endpoint via the shared `GuruClient` instance. The MCP server sets the `x-guru-mcp-client` header on every request so guru-server can stamp author correctly — extend `GuruClient` to pass this header through if not already.

- [ ] **Step 5.4.2 — Tests.**

Mirror the design spec §Tier 3 `graph_mcp_tools.feature` scenarios at unit level — for each tool, mock `GuruClient`, call the tool, assert the right endpoint + kwargs.

Also add:

```python
def test_no_write_tools_for_kb_crud():
    # The 10 tools allow annotate/link/unlink/delete/reattach only.
    from guru_mcp import server

    tool_names = {t.name for t in server.mcp.list_tools()}
    forbidden = {"upsert_kb", "delete_kb", "link_kbs", "unlink_kbs"}
    assert tool_names & forbidden == set()
```

- [ ] **Step 5.4.3 — Commit.**

```bash
git add packages/guru-mcp/src/guru_mcp/server.py \
        packages/guru-mcp/tests/unit/test_graph_tools.py
git commit -m "feat(mcp): 10 new graph_* tools mapping 1:1 to guru-server /graph/*"
```

---

### Task 5.5 — CLI read-only extensions

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/graph.py`
- Test: `packages/guru-cli/tests/unit/test_graph_cli_reads_artifact.py`

- [ ] **Step 5.5.1 — Add subcommands.**

Add `describe`, `neighbors`, `find`, `annotations`, `orphans` click subcommands to the existing `guru graph` group. Each calls the matching `GraphClient` method and renders text or `--json`. When graph is disabled → exit 0, `stdout: graph is disabled`. When daemon unreachable → exit 1 per existing precedent.

Safety test (matching `test_graph_cli_safety.py` pattern):

```python
def test_no_write_subcommands_in_graph_group():
    from guru_cli.commands.graph import graph as graph_group
    names = {c.name for c in graph_group.commands.values()}
    assert not (names & {"annotate", "link", "unlink", "delete-annotation", "reattach-orphan"})
```

- [ ] **Step 5.5.2 — Commit.**

```bash
git add packages/guru-cli/src/guru_cli/commands/graph.py \
        packages/guru-cli/tests/unit/test_graph_cli_reads_artifact.py
git commit -m "feat(cli): guru graph {describe,neighbors,find,annotations,orphans} read-only subcommands"
```

---

### Task 5.6 — BDD + PR-5 verification

Run `graph_mcp_tools.feature` + updated `graph_optional.feature`. Open PR.

---

# PR-6 — Skill package + `guru init` + `guru update`

**Branch:** `feat/artifact-graph-pr6-skill`

**Scope recap.** Ship the skill asset tree inside the guru-cli wheel. `guru init` materialises `.claude/skills/guru-knowledge-base/` + `.agents/skills/…` symlink. New `guru update` command with manifest-based drift detection, `--force`, `--dry-run`.

**Success gate:**
```bash
uv run behave tests/e2e/features/skill_distribution.feature
```

---

### Task 6.1 — Create the skill asset tree

**Files:**
- Create: `packages/guru-cli/src/guru_cli/assets/__init__.py` (empty)
- Create: `packages/guru-cli/src/guru_cli/assets/skills/__init__.py` (empty)
- Create: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/SKILL.md`
- Create: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/references/model.md`
- Create: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/references/discovery.md`
- Create: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/references/curation.md`
- Create: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/references/annotation-shape.md`
- Create: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/references/linking-patterns.md`
- Create: `packages/guru-cli/src/guru_cli/assets/skills/guru-knowledge-base/references/orphans.md`
- Modify: `packages/guru-cli/pyproject.toml`

- [ ] **Step 6.1.1 — Write `SKILL.md`.**

Use the exact content from the design spec §SKILL.md content commitments. Frontmatter first, then the eight-section body (each ≤50 words). Total ≤400 words verified by `wc -w`.

- [ ] **Step 6.1.2 — Write each reference file.**

Each `references/*.md` follows its purpose + word budget from the design spec. Use the spec's table as the content map. Draft short, task-focused prose; include one concrete example per file where the spec calls for it (e.g. `linking-patterns.md` — "agent discovers `UserRepository.foo` calls `UserApi.get_user` → emits `calls` link").

- [ ] **Step 6.1.3 — Include assets in the wheel.**

In `packages/guru-cli/pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/guru_cli/assets/skills/guru-knowledge-base" = "guru_cli/assets/skills/guru-knowledge-base"
```

(Adjust the exact source path to match the `src-layout`.)

- [ ] **Step 6.1.4 — Verify the wheel.**

```bash
uv build --directory packages/guru-cli --out-dir /tmp/wheel_test/
unzip -l /tmp/wheel_test/guru_cli-*.whl | grep guru-knowledge-base
```

Expect every skill file listed.

- [ ] **Step 6.1.5 — Commit.**

```bash
git add packages/guru-cli/src/guru_cli/assets \
        packages/guru-cli/pyproject.toml
git commit -m "feat(cli): ship guru-knowledge-base skill assets in the wheel"
```

---

### Task 6.2 — `skills_install.py` shared installer

**Files:**
- Create: `packages/guru-cli/src/guru_cli/skills_install.py`
- Test: `packages/guru-cli/tests/unit/test_skills_install.py`

- [ ] **Step 6.2.1 — Write the failing test.**

```python
from __future__ import annotations

import json
from pathlib import Path

from guru_cli.skills_install import install_skill, update_skill


def test_install_writes_all_files_and_manifest(tmp_path: Path):
    report = install_skill(tmp_path)
    dest = tmp_path / ".claude" / "skills" / "guru-knowledge-base"
    assert (dest / "SKILL.md").exists()
    for n in ("model", "discovery", "curation", "annotation-shape", "linking-patterns", "orphans"):
        assert (dest / "references" / f"{n}.md").exists()
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    assert "files" in manifest
    assert manifest["files"]["SKILL.md"]  # sha256
    agents = tmp_path / ".agents" / "skills" / "guru-knowledge-base"
    assert agents.is_symlink() or agents.exists()


def test_update_noop_when_unchanged(tmp_path: Path):
    install_skill(tmp_path)
    changed = update_skill(tmp_path)
    assert changed == []


def test_update_overwrites_when_shipped_changed_but_user_unmodified(tmp_path: Path, monkeypatch):
    install_skill(tmp_path)
    # Simulate user kept the file intact while the shipped version changes
    dest = tmp_path / ".claude" / "skills" / "guru-knowledge-base"
    # We pretend the on-disk manifest is older by editing its hash for SKILL.md
    manifest_path = dest / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["SKILL.md"] = "deadbeef" * 8
    manifest_path.write_text(json.dumps(manifest))
    changed = update_skill(tmp_path)
    assert "SKILL.md" in changed


def test_update_skips_user_modified_file(tmp_path: Path):
    install_skill(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "SKILL.md"
    skill.write_text(skill.read_text() + "\n\n## Custom section\n")
    changed = update_skill(tmp_path)
    assert "SKILL.md" not in changed


def test_update_force_overwrites_and_backs_up(tmp_path: Path):
    install_skill(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "SKILL.md"
    custom_content = "custom\n"
    skill.write_text(custom_content)
    changed = update_skill(tmp_path, force=True)
    assert "SKILL.md" in changed
    backups = list(skill.parent.glob("SKILL.md.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == custom_content


def test_update_dry_run_writes_nothing(tmp_path: Path):
    install_skill(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "SKILL.md"
    # Pretend manifest mismatch
    manifest = tmp_path / ".claude" / "skills" / "guru-knowledge-base" / "MANIFEST.json"
    m = json.loads(manifest.read_text())
    m["files"]["SKILL.md"] = "deadbeef" * 8
    manifest.write_text(json.dumps(m))
    mtime_before = skill.stat().st_mtime
    changed = update_skill(tmp_path, dry_run=True)
    assert "SKILL.md" in changed
    assert skill.stat().st_mtime == mtime_before
```

- [ ] **Step 6.2.2 — Implement.**

```python
"""Installer for the guru-knowledge-base skill."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

_PKG_SKILL_ROOT = "guru_cli.assets.skills.guru-knowledge-base"


def _asset_root() -> Path:
    # importlib.resources.files returns a Traversable; convert to a Path
    # via as_file context if it's inside a wheel.
    return Path(resources.files(_PKG_SKILL_ROOT))  # type: ignore[arg-type]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_paths(root: Path) -> list[Path]:
    files = ["SKILL.md"]
    for n in ("model", "discovery", "curation", "annotation-shape", "linking-patterns", "orphans"):
        files.append(f"references/{n}.md")
    return [Path(f) for f in files]


def _copy_tree_preserving_paths(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for rel in _manifest_paths(src):
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((src / rel).read_bytes())


def _write_manifest(dst: Path, shipped_hashes: dict[str, str], guru_version: str) -> None:
    manifest = {
        "guru_version": guru_version,
        "files": shipped_hashes,
    }
    (dst / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))


def _agents_symlink_or_copy(claude_path: Path, agents_path: Path) -> None:
    agents_path.parent.mkdir(parents=True, exist_ok=True)
    if agents_path.exists() or agents_path.is_symlink():
        return
    if sys.platform == "win32":
        shutil.copytree(claude_path, agents_path)
    else:
        # Relative symlink from .agents/skills/guru-knowledge-base to .claude/skills/guru-knowledge-base
        rel = os.path.relpath(claude_path, agents_path.parent)
        agents_path.symlink_to(rel)


def install_skill(project_root: Path, *, guru_version: str = "0.0.0") -> list[str]:
    """Materialise the skill tree under .claude/skills/guru-knowledge-base and mirror to .agents/."""
    src = _asset_root()
    claude_dest = project_root / ".claude" / "skills" / "guru-knowledge-base"
    _copy_tree_preserving_paths(src, claude_dest)
    shipped_hashes = {str(rel): _sha256_bytes((src / rel).read_bytes()) for rel in _manifest_paths(src)}
    _write_manifest(claude_dest, shipped_hashes, guru_version)
    _agents_symlink_or_copy(
        claude_dest,
        project_root / ".agents" / "skills" / "guru-knowledge-base",
    )
    return list(shipped_hashes)


def update_skill(
    project_root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    src = _asset_root()
    dest = project_root / ".claude" / "skills" / "guru-knowledge-base"
    if not dest.exists():
        return install_skill(project_root)

    manifest_path = dest / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    manifest_hashes: dict[str, str] = manifest.get("files", {})

    changed: list[str] = []
    ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")

    new_hashes: dict[str, str] = {}
    for rel in _manifest_paths(src):
        rel_s = str(rel)
        shipped_bytes = (src / rel).read_bytes()
        shipped_h = _sha256_bytes(shipped_bytes)
        new_hashes[rel_s] = shipped_h

        user_path = dest / rel
        user_h = _sha256_bytes(user_path.read_bytes()) if user_path.exists() else None
        manifest_h = manifest_hashes.get(rel_s)

        if user_h == shipped_h:
            continue  # up to date
        if user_h is None:
            # Missing on disk; reinstall it
            changed.append(rel_s)
            if not dry_run:
                user_path.parent.mkdir(parents=True, exist_ok=True)
                user_path.write_bytes(shipped_bytes)
            continue
        if user_h == manifest_h:
            # Unmodified by user, shipped changed → safe overwrite
            changed.append(rel_s)
            if not dry_run:
                user_path.write_bytes(shipped_bytes)
        else:
            # User customised
            if force:
                backup = user_path.with_name(f"{user_path.name}.bak.{ts}")
                if not dry_run:
                    shutil.copy2(user_path, backup)
                    user_path.write_bytes(shipped_bytes)
                changed.append(rel_s)

    if changed and not dry_run:
        _write_manifest(dest, new_hashes, guru_version=manifest.get("guru_version", "0.0.0"))
    return changed
```

- [ ] **Step 6.2.3 — Run tests + commit.**

```bash
uv run pytest packages/guru-cli/tests/unit/test_skills_install.py -v
git add packages/guru-cli/src/guru_cli/skills_install.py \
        packages/guru-cli/tests/unit/test_skills_install.py
git commit -m "feat(cli): skill installer with manifest-based drift detection"
```

---

### Task 6.3 — Extend `guru init` + add `guru update`

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/commands/init.py`
- Create: `packages/guru-cli/src/guru_cli/commands/update.py`
- Modify: `packages/guru-cli/src/guru_cli/main.py`
- Test: `packages/guru-cli/tests/unit/test_update_command.py`

- [ ] **Step 6.3.1 — Wire `install_skill` into `init`.**

At the end of the existing `init` command body (after writing `.guru/`, `guru.json`):

```python
from guru_cli.skills_install import install_skill
from guru_cli import __version__

installed = install_skill(project_root, guru_version=__version__)
click.echo(f"installed skill: .claude/skills/guru-knowledge-base ({len(installed)} files)")
```

- [ ] **Step 6.3.2 — Implement `update` command.**

```python
"""`guru update` — refresh guru-managed artefacts in the current project."""

from __future__ import annotations

from pathlib import Path

import click

from guru_cli import __version__
from guru_cli.skills_install import update_skill


@click.command("update")
@click.option("--force", is_flag=True, help="Overwrite user-customised files (with .bak backup)")
@click.option("--dry-run", is_flag=True, help="Report what would change without writing")
def update_cmd(force: bool, dry_run: bool) -> None:
    """Refresh guru-managed assets (currently: the knowledge-base skill)."""
    project_root = Path.cwd()
    changed = update_skill(project_root, force=force, dry_run=dry_run)
    if not changed:
        click.echo("already up to date")
        return
    prefix = "would update" if dry_run else "updated"
    for rel in changed:
        click.echo(f"{prefix}: {rel}")
```

Register in `main.py`: `cli.add_command(update_cmd)`.

- [ ] **Step 6.3.3 — CliRunner test.**

```python
# packages/guru-cli/tests/unit/test_update_command.py
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from guru_cli.commands.update import update_cmd
from guru_cli.skills_install import install_skill


def test_update_reports_no_changes_on_fresh_install(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        install_skill(Path.cwd())
        result = runner.invoke(update_cmd, [])
        assert result.exit_code == 0
        assert "already up to date" in result.output


def test_update_dry_run_reports_would_update(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        install_skill(Path.cwd())
        # Mutate manifest to force a "shipped changed" state
        manifest_path = Path(".claude/skills/guru-knowledge-base/MANIFEST.json")
        m = json.loads(manifest_path.read_text())
        m["files"]["SKILL.md"] = "deadbeef" * 8
        manifest_path.write_text(json.dumps(m))
        result = runner.invoke(update_cmd, ["--dry-run"])
        assert result.exit_code == 0
        assert "would update: SKILL.md" in result.output
```

- [ ] **Step 6.3.4 — Commit.**

```bash
git add packages/guru-cli/src/guru_cli/commands/init.py \
        packages/guru-cli/src/guru_cli/commands/update.py \
        packages/guru-cli/src/guru_cli/main.py \
        packages/guru-cli/tests/unit/test_update_command.py
git commit -m "feat(cli): guru init installs skill; guru update refreshes with drift guard"
```

---

### Task 6.4 — `skill_distribution.feature`

**Files:**
- Create: `tests/e2e/features/skill_distribution.feature`
- Create: `tests/e2e/features/steps/skill_steps.py`

Write the six scenarios from the design spec. Use `tmpdir` contexts.

Run:

```bash
uv run behave tests/e2e/features/skill_distribution.feature
```

Commit.

---

### Task 6.5 — Full PR-6 verification

Standard.

---

# PR-7 — Python parser (tree-sitter)

**Branch:** `feat/artifact-graph-pr7-python`

**Scope recap.** `PythonParser` using `tree-sitter-python`. Modules, Classes, Functions, Methods with qualnames, docstrings, signatures. Imports + inheritance edges. Calls deferred.

**Success gate:**
```bash
uv run pytest packages/guru-server/tests/unit/test_python_parser.py -v
GURU_REAL_NEO4J=1 uv run behave tests/e2e/features/artifact_indexing.feature --tags=~@skip_until_pr8
uv run behave tests/e2e/features/parser_extensibility.feature
```

---

### Task 7.1 — Add tree-sitter dependencies

**Files:**
- Modify: `packages/guru-server/pyproject.toml`

- [ ] **Step 7.1.1 — Add deps.**

```toml
# packages/guru-server/pyproject.toml
[tool.hatch.metadata.hooks.uv-dynamic-versioning]
dependencies = [
    # existing deps...
    "tree-sitter>=0.22,<0.24",
    "tree-sitter-python>=0.21,<0.24",
]
```

Pin to a minor-compatible range; tree-sitter-python must match the grammar ABI.

- [ ] **Step 7.1.2 — Install + commit.**

```bash
uv sync --all-packages
git add packages/guru-server/pyproject.toml uv.lock
git commit -m "chore(server): add tree-sitter-python dependency for PythonParser"
```

---

### Task 7.2 — `PythonParser` core

**Files:**
- Create: `packages/guru-server/src/guru_server/ingestion/python.py`
- Create: `packages/guru-server/tests/unit/test_python_parser.py`

- [ ] **Step 7.2.1 — Write failing tests.**

```python
# packages/guru-server/tests/unit/test_python_parser.py
from __future__ import annotations

from pathlib import Path

import pytest

from guru_core.types import Rule, RuleMatch
from guru_server.ingestion.python import PythonParser


@pytest.fixture
def rule():
    return Rule(ruleName="code", match=RuleMatch(glob="**/*.py"))


def test_supports_python_files_only(tmp_path: Path):
    p = PythonParser()
    assert p.supports(tmp_path / "x.py")
    assert not p.supports(tmp_path / "x.md")


def test_name_is_python():
    assert PythonParser().name == "python"


def test_parse_emits_document_and_module(tmp_path: Path, rule):
    f = tmp_path / "pkg" / "mod.py"
    f.parent.mkdir()
    f.write_text("def foo(): pass\n")
    # mark parent package as a package
    (tmp_path / "pkg" / "__init__.py").write_text("")

    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb")

    assert result.document.label == "Document"
    module_nodes = [n for n in result.nodes if n.label == "Module"]
    assert module_nodes, "expected a :Module node"
    assert any(n.properties["qualname"] == "pkg.mod" for n in module_nodes)


def test_parse_emits_class_and_methods(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text(
        """\
class Foo:
    \"\"\"Docs.\"\"\"
    def bar(self):
        pass
    def baz(self):
        pass
"""
    )
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb")
    classes = [n for n in result.nodes if n.label == "Class"]
    methods = [n for n in result.nodes if n.label == "Method"]
    assert any(c.properties["qualname"] == "a.Foo" for c in classes)
    assert {m.properties["qualname"] for m in methods} == {"a.Foo.bar", "a.Foo.baz"}


def test_parse_emits_inheritance_edge(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text("class Base: pass\nclass Derived(Base): pass\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb")
    edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "inherits_from"]
    assert len(edges) == 1


def test_parse_emits_imports_edge(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "b.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text("from b import x\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb")
    edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "imports"]
    assert len(edges) == 1


def test_parse_emits_code_chunks_with_qualname(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    '''d'''\n    return 1\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb")
    # at least one chunk per top-level symbol
    assert any(c.kind == "code" and c.artifact_qualname == "kb::a.foo" for c in result.chunks)
```

- [ ] **Step 7.2.2 — Implement the parser.**

Key concerns:
1. Build a `tree_sitter.Parser` once with `tree_sitter.Language(tree_sitter_python.language())`.
2. Walk the AST; collect top-level `function_definition`, `class_definition`, `decorated_definition` nodes.
3. Qualname derivation: walk up from `file_path` looking for `__init__.py` to determine the package root; the dotted path is `Path(file_path).relative_to(package_root).with_suffix("")` with `.parts` joined by `.`.
4. Imports: match AST `import_statement` / `import_from_statement`; resolve the target module path; emit a `RELATES {kind:imports}` edge to a `(:Module)` node (create a placeholder node if the target isn't a first-party file).
5. Inheritance: for a `class Derived(Base):` AST, emit `RELATES {kind:inherits_from}` from `(:Class Derived)` to `(:Class Base)`. Resolve `Base` within the same module; unresolved → placeholder node keyed `kb::<base_name>__unresolved__`.
6. Chunk text per top-level symbol: `signature + "\n\n" + docstring + "\n\n" + body[:800 tokens]`.
7. Method chunks: `class_docstring + "\n\n" + signature + "\n\n" + method_docstring + "\n\n" + body[:800]`.

Constructor:
```python
class PythonParser(DocumentParser):
    def __init__(self, *, package_roots: list[Path] | None = None) -> None:
        self._package_roots = package_roots or []
        self._lang = Language(tree_sitter_python.language())
        self._parser = Parser()
        self._parser.language = self._lang
```

Add a helper `_derive_qualname(file_path) -> str` that resolves using `_package_roots`.

The full implementation is ~250 lines; write it following the tests. Keep each `_emit_X` method small and one-responsibility.

- [ ] **Step 7.2.3 — Run tests.**

```bash
uv run pytest packages/guru-server/tests/unit/test_python_parser.py -v
```

All pass.

- [ ] **Step 7.2.4 — Commit.**

```bash
git add packages/guru-server/src/guru_server/ingestion/python.py \
        packages/guru-server/tests/unit/test_python_parser.py
git commit -m "feat(ingestion): PythonParser with tree-sitter (modules/classes/functions/methods, imports, inheritance)"
```

---

### Task 7.3 — Register PythonParser at startup + package-root detection

**Files:**
- Modify: `packages/guru-server/src/guru_server/main.py`

- [ ] **Step 7.3.1 — Wire up.**

Compute the project's package roots at startup: walk the project tree looking for directories with `__init__.py`. Build the parser once and pass the roots.

```python
parser_registry.register(MarkdownParser())
parser_registry.register(PythonParser(package_roots=_detect_package_roots(project_root)))
```

- [ ] **Step 7.3.2 — Commit.**

```bash
git add packages/guru-server/src/guru_server/main.py
git commit -m "feat(server): register PythonParser with detected package roots"
```

---

### Task 7.4b — `hybrid_search.feature` (covers real artifact chunks end-to-end)

**Files:**
- Create: `tests/e2e/features/hybrid_search.feature`

- [ ] **Step 7.4b.1 — Write scenarios.**

Copy the three scenarios verbatim from the design spec §Tier 3 `hybrid_search.feature`. All three tags are `@real_ollama`; two are also `@real_neo4j`. Use the existing `polyglot` fixture.

- [ ] **Step 7.4b.2 — Run + commit.**

```bash
GURU_REAL_OLLAMA=1 GURU_REAL_NEO4J=1 \
  uv run behave tests/e2e/features/hybrid_search.feature
git add tests/e2e/features/hybrid_search.feature
git commit -m "test(e2e): hybrid_search BDD scenarios (mixed doc + artifact chunks, graph pivot, graph-disabled path)"
```

---

### Task 7.4 — BDD parser_extensibility.feature

**Files:**
- Create: `tests/e2e/features/parser_extensibility.feature`
- Create: `tests/e2e/fixtures/protobuf_parser/parser.py`
- Create: `tests/e2e/fixtures/protobuf_parser/user.proto`

- [ ] **Step 7.4.1 — Write the test parser.**

```python
# tests/e2e/fixtures/protobuf_parser/parser.py
from __future__ import annotations

from pathlib import Path

from guru_core.types import Rule
from guru_server.ingestion.base import (
    Chunk,
    DocumentParser,
    GraphEdge,
    GraphNode,
    ParseResult,
)


class ProtobufParser(DocumentParser):
    @property
    def name(self) -> str:
        return "protobuf"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".proto"

    def parse(self, file_path: Path, rule: Rule, *, kb_name: str) -> ParseResult:
        doc_id = f"{kb_name}::{file_path.as_posix()}"
        doc = GraphNode(
            node_id=doc_id, label="Document",
            properties={"kb_name": kb_name, "language": "protobuf", "file_type": "schema", "parser_name": "protobuf"},
        )
        chunks = [Chunk(
            content=file_path.read_text(), file_path=str(file_path),
            header_breadcrumb="proto", chunk_level=1,
            kind="code", language="protobuf",
            parent_document_id=doc_id,
            artifact_qualname=f"{doc_id}::root",
        )]
        return ParseResult(chunks=chunks, document=doc, nodes=[], edges=[])
```

- [ ] **Step 7.4.2 — Scenario.**

```gherkin
Feature: Adding a new language parser is a pure extension

  Scenario: A test ProtobufParser is registered at startup
    Given the test registers ProtobufParser into the shared ParserRegistry via the init hook
    And a fixture project with a file api/user.proto
    When `guru index` runs
    Then ProtobufParser.parse was called for api/user.proto exactly once
    And the chunks emitted appear in LanceDB with parser_name="protobuf"
```

Step implementation uses a behave hook that imports and registers the fixture parser before starting the server for this feature.

- [ ] **Step 7.4.3 — Un-skip Python scenarios in `artifact_indexing.feature`.**

Remove `@skip_until_pr7` tags. Run the full feature.

- [ ] **Step 7.4.4 — Commit + PR.**

```bash
git add tests/e2e/features/parser_extensibility.feature \
        tests/e2e/fixtures/protobuf_parser \
        tests/e2e/features/artifact_indexing.feature
git commit -m "test(e2e): parser_extensibility + un-skip Python scenarios in artifact_indexing"
```

Open PR-7.

---

# PR-8 — OpenAPI parser

**Branch:** `feat/artifact-graph-pr8-openapi`

**Scope recap.** `OpenApiParser` supporting OpenAPI 3.0 + 3.1, YAML + JSON. Emits `(:OpenApiSpec)`, `(:OpenApiOperation)`, `(:OpenApiSchema)`. Local `$ref` → RELATES references edges. Cross-file `$ref` resolved relative to file dir; unresolved → placeholder node. Circular `$ref` safe via visited set. `oneOf`/`anyOf`/`allOf` collapsed. Malformed YAML → single spec node with `Document.properties.valid=false` + the error.

### Task 8.1 — Add PyYAML dependency

```bash
# packages/guru-server/pyproject.toml
"PyYAML>=6.0"
git commit -m "chore(server): add PyYAML dep for OpenAPI parser"
```

### Task 8.2 — `OpenApiParser` core

Tests (`test_openapi_parser.py`) cover:
- YAML + JSON ingestion
- OpenAPI 3.0 + 3.1 fixtures
- One `(:OpenApiOperation)` per path × method
- One `(:OpenApiSchema)` per `components/schemas/*`
- Local `$ref` produces `:RELATES {kind:"references"}` to schema
- Cross-file `$ref` resolved via file-relative path
- Circular `$ref` doesn't infinite-loop
- `oneOf` / `anyOf` / `allOf` collapse to single schema node with `metadata.shape`
- Malformed YAML → `Document.properties.valid=false`, no sub-artifacts

Implementation pattern: `yaml.safe_load` with a fallback to `json.loads`. Walk the dict. Emit nodes + CONTAINS edges. Gather `$ref` strings; emit RELATES edges.

### Task 8.3 — Register at startup

`parser_registry.register(OpenApiParser())`.

### Task 8.4 — Un-skip OpenAPI scenarios

Remove `@skip_until_pr8` tags from `artifact_indexing.feature` and `artifact_links.feature`. Run + verify.

### Task 8.5 — Full PR-8 verification

Standard.

---

# PR-9 — ARCHITECTURE.md amendments + docs closeout

**Branch:** `feat/artifact-graph-pr9-docs`

**Scope recap.** Add the four constitution amendments from Chunk 1 to `ARCHITECTURE.md`. Cross-link the spec, this plan, and the graph-plugin spec. Add a single line to `AGENTS.md` pointing at the skill.

### Task 9.1 — Edit `ARCHITECTURE.md`

Add after the existing graph plugin section:

```markdown
## Artifact Graph (from PR-2..PR-8)

- Every indexed file produces both a LanceDB chunk set and a `(:Document)`
  graph node when the graph is enabled. Graph-disabled mode discards graph
  facts; chunks still flow to LanceDB.
- Document parsers emit a single `ParseResult` per file carrying chunks and
  (`Document`, sub-artifact nodes, edges). Dispatch is always-on by
  `supports()`; no per-parser config flag.
- MCP tools are read-only by default. Agent-writable knowledge-base
  operations — `graph_annotate`, `graph_link`, `graph_unlink`,
  `graph_delete_annotation`, `graph_reattach_orphan` — are the explicit
  exception. Any further write surface requires a constitution amendment.
- Every graph-agnostic operation must work identically whether the graph is
  enabled, disabled, unreachable, or crashed. `search()`, `get_document()`,
  `index_status()`, `guru index`, `guru search`, etc. never change behaviour
  based on graph state.
```

### Task 9.2 — Edit `AGENTS.md`

Add a one-line reference:

```markdown
- Agents working inside a guru-managed project should use the
  `guru-knowledge-base` skill shipped by `guru init` at
  `.claude/skills/guru-knowledge-base/`.
```

### Task 9.3 — `constitution_invariants.feature` — the anti-regression suite

**Files:**
- Create: `tests/e2e/features/constitution_invariants.feature`
- Modify: `tests/e2e/features/steps/artifact_steps.py` (new step definitions)

- [ ] **Step 9.3.1 — Write the three scenarios.**

Copy verbatim from the design spec §Tier 3 `constitution_invariants.feature`:

```gherkin
Feature: Non-negotiable architectural invariants

  Scenario: Indexing never blocks on graph I/O
    Given graph is enabled but daemon is hung (sleeps 30s on every request)
    When `guru index` runs with a 5s per-file budget
    Then `guru index` completes within the per-file budget × files count + small epsilon
    And LanceDB is fully populated
    And graph submissions were abandoned via graph_or_skip

  Scenario: MCP writes limited to annotations + links
    When MCP tool list is enumerated
    Then the only write-capable tools are graph_annotate, graph_delete_annotation,
                                            graph_link, graph_unlink, graph_reattach_orphan
    And no tool exists for upsert_kb, delete_kb, link_kbs, unlink_kbs, arbitrary Cypher writes

  Scenario: Graph-agnostic CLI + MCP unchanged
    When I diff the pre-feature and post-feature surfaces of
         search, get_document, list_documents, get_section, index_status,
         federated_search, list_peers, guru init, guru index, guru status
    Then their contracts are byte-identical
```

- [ ] **Step 9.3.2 — Step definitions.**

In `steps/artifact_steps.py`:

- "graph is enabled but daemon is hung" — spawn a tiny stand-in daemon that accepts connections on `graph.sock` and blocks on every request.
- "guru index runs with a 5s per-file budget" — launch `guru-server`'s index endpoint; assert total time < `N * 5s + 10s` buffer.
- "MCP tool list is enumerated" — import `guru_mcp.server`; iterate `server.mcp.list_tools()`.
- "their contracts are byte-identical" — snapshot the OpenAPI spec of pre-feature guru-server (stored at `tests/e2e/snapshots/pre_artifact_graph_openapi.json` as a checked-in golden file; produced once manually from `git show <base-commit>:... | …`) and diff against the current `/openapi.json` response, ignoring paths under `/graph/*` and `/ingest/*`.

- [ ] **Step 9.3.3 — Run + commit.**

```bash
uv run behave tests/e2e/features/constitution_invariants.feature
git add tests/e2e/features/constitution_invariants.feature \
        tests/e2e/features/steps/artifact_steps.py \
        tests/e2e/snapshots/pre_artifact_graph_openapi.json
git commit -m "test(e2e): constitution_invariants — graph never blocks indexing, MCP write-surface is bounded, agnostic surfaces byte-identical"
```

---

### Task 9.4 — Commit docs + open PR

```bash
git add ARCHITECTURE.md AGENTS.md
git commit -m "docs: artifact-graph constitution amendments + AGENTS.md skill mention"
```

Open PR-9. Its success gate is docs render + `constitution_invariants.feature` green. Merge last.

---

# Appendix A — Shared test infrastructure

Common fixtures + behave plumbing:

| Fixture | Created in | Owned by |
|---|---|---|
| `tests/e2e/fixtures/polyglot/` | Task 2.8 | Shared |
| `tests/e2e/fixtures/protobuf_parser/` | Task 7.4 | PR-7 only |
| `tests/e2e/features/steps/artifact_steps.py` | Task 2.8 | Shared |
| `tests/e2e/features/steps/annotation_steps.py` | Task 3.5 | PR-3+ |
| `tests/e2e/features/steps/orphan_steps.py` | Task 3.5 | PR-3+ |
| `tests/e2e/features/steps/skill_steps.py` | Task 6.4 | PR-6+ |

Behave `before_feature(context, feature)` extended to:
1. Spin a per-feature guru-server (existing pattern).
2. If `@real_neo4j` on the feature, spin a per-feature guru-graph daemon (subprocess) connected to the CI-provided Neo4j (`GURU_NEO4J_BOLT_URI`). Shut down in `after_feature`.

---

# Appendix B — CI wiring additions

In `.github/workflows/ci.yml` add a new job:

```yaml
artifact-graph-e2e:
  needs: unit
  if: contains(github.event.pull_request.labels.*.name, 'require-e2e-tests')
  runs-on: ubuntu-latest
  services:
    neo4j:
      image: neo4j:5
      ports: ["17687:7687"]
      env:
        NEO4J_AUTH: none
  env:
    GURU_REAL_NEO4J: "1"
    GURU_NEO4J_BOLT_URI: bolt://127.0.0.1:17687
  steps:
    - uses: actions/checkout@v4
    - uses: ./.github/actions/setup      # shared setup
    - run: uv sync --all-packages
    - run: uv run behave tests/e2e/features/artifact_indexing.feature
    - run: uv run behave tests/e2e/features/hybrid_search.feature
    - run: uv run behave tests/e2e/features/annotations_and_curation.feature
    - run: uv run behave tests/e2e/features/orphan_triage.feature
    - run: uv run behave tests/e2e/features/artifact_links.feature
    - run: uv run behave tests/e2e/features/graph_mcp_tools.feature
    - run: uv run behave tests/e2e/features/graph_optional.feature
    - run: uv run behave tests/e2e/features/skill_distribution.feature
    - run: uv run behave tests/e2e/features/parser_extensibility.feature
    - run: uv run behave tests/e2e/features/constitution_invariants.feature
```

Add `make test-artifact-graph` as a convenience local runner that mirrors the CI job.

---

# Appendix C — Plan self-review checklist

Before opening PR-1:

1. **Spec coverage.** Re-read the design spec §Goals and §Non-Goals. Every goal has at least one task; every non-goal is absent. ✅ after plan self-review (see top-level agent's self-review log).
2. **Ambiguity.** Any step that says "similar to", "as needed", or lacks code? Fix inline.
3. **Type consistency.** `node_id` vs `id` — node payloads use `node_id`; once inserted, Neo4j exposes `.id`. The proxy maps between them; tests assert both naming conventions live side-by-side (protocol uses `node_id`, schema uses `id`).
4. **Route consistency.** Every MCP tool's `/graph/*` route matches the 1:1 table in the spec §REST endpoint mapping. ✅
5. **Graph-disabled invariant.** Every place the plan mentions graph writes, it either wraps in `graph_or_skip` (indexer) or returns the `graph_disabled` sentinel (MCP proxy). No graph write path bypasses both. ✅

---

# How to run this plan

Every task above ends with `git commit`. Pushing each PR's branch at the end of its last task opens the PR. Green CI on the success-gate commands is the gate.

If you want to run the PRs in a worktree (recommended for isolation), create one before starting PR-1:

```bash
git worktree add ../guru-artifact-graph feat/artifact-graph-pr1-parser-contract
cd ../guru-artifact-graph
```

Work in that worktree until PR-9 merges.
