"""Python source parser using tree-sitter.

Emits:
  (:Document) — the file
  (:Module)   — the Python module (qualname-keyed)
  (:Class)    — each top-level class
  (:Function) — each top-level function
  (:Method)   — each method on a class

Plus CONTAINS edges (Document -> Module -> Class -> Method, Module -> Function)
and RELATES edges:
  - {kind:"imports"} for every ``import X`` / ``from X import …``
  - {kind:"inherits_from"} for every ``class Derived(Base):``

Unresolved import targets and unresolved base classes get placeholder nodes
with ``unresolved=True`` so downstream queries don't dangle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from guru_core.types import Rule
from guru_server.ingestion.base import (
    Chunk,
    DocumentParser,
    GraphEdge,
    GraphNode,
    ParseResult,
)

_CHUNK_BODY_LIMIT = 800  # chars per chunk body slice; keeps embeddings sane


@dataclass
class _Symbol:
    """Internal representation of a Python symbol parsed from the AST."""

    name: str
    kind: str  # "class" | "function" | "method"
    qualname: str
    docstring: str | None
    signature: str
    body_text: str
    parent_qualname: str | None  # for methods: enclosing class qualname


class PythonParser(DocumentParser):
    @property
    def name(self) -> str:
        return "python"

    def __init__(self, *, package_roots: list[Path] | None = None) -> None:
        self._package_roots = package_roots or []
        self._lang = Language(tree_sitter_python.language())
        self._parser = Parser()
        self._parser.language = self._lang

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def parse(
        self, file_path: Path, rule: Rule, *, kb_name: str, rel_path: str = ""
    ) -> ParseResult:
        # If rel_path wasn't supplied (unit-test calls), derive from file name
        # so the Document.id stays well-formed.
        if not rel_path:
            rel_path = file_path.name

        source_bytes = file_path.read_bytes()
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        module_qualname = self._derive_module_qualname(file_path)
        module_id = f"{kb_name}::{module_qualname}"
        document_id = f"{kb_name}::{rel_path}"

        document_node = GraphNode(
            node_id=document_id,
            label="Document",
            properties={
                "kb_name": kb_name,
                "relative_path": rel_path,
                "absolute_path": str(file_path),
                "language": "python",
                "file_type": "code",
                "parser_name": "python",
                "size_bytes": len(source_bytes),
            },
        )

        module_docstring = self._module_docstring(root, source_bytes)
        module_node = GraphNode(
            node_id=module_id,
            label="Module",
            properties={
                "kb_name": kb_name,
                "qualname": module_qualname,
                "name": module_qualname.rsplit(".", 1)[-1],
                "docstring": module_docstring or "",
            },
        )

        nodes: list[GraphNode] = [module_node]
        edges: list[GraphEdge] = [
            GraphEdge(from_id=document_id, to_id=module_id, rel_type="CONTAINS"),
        ]
        chunks: list[Chunk] = [
            self._module_chunk(
                module_qualname=module_qualname,
                document_id=document_id,
                kb_name=kb_name,
                docstring=module_docstring,
            ),
        ]

        # Imports -> RELATES(imports). Deduplicate so `import a, b` followed by
        # another `import a` doesn't emit duplicate placeholder modules.
        seen_module_ids: set[str] = {module_id}
        for target_qualname in self._collect_imports(root, source_bytes):
            target_id = self._resolve_module_id(target_qualname, kb_name)
            placeholder = self._maybe_external_module(target_id, target_qualname, kb_name)
            if placeholder is not None and target_id not in seen_module_ids:
                nodes.append(placeholder)
                seen_module_ids.add(target_id)
            edges.append(
                GraphEdge(
                    from_id=module_id,
                    to_id=target_id,
                    rel_type="RELATES",
                    kind="imports",
                )
            )

        # Top-level functions and classes
        for sym in self._collect_top_level_symbols(root, source_bytes, module_qualname):
            sym_id = f"{kb_name}::{sym.qualname}"
            label = "Class" if sym.kind == "class" else "Function"
            sym_node = GraphNode(
                node_id=sym_id,
                label=label,
                properties={
                    "kb_name": kb_name,
                    "qualname": sym.qualname,
                    "name": sym.name,
                    "docstring": sym.docstring or "",
                    "signature": sym.signature,
                },
            )
            nodes.append(sym_node)
            edges.append(GraphEdge(from_id=module_id, to_id=sym_id, rel_type="CONTAINS"))
            chunks.append(self._symbol_chunk(sym, document_id, kb_name))

            if sym.kind == "class":
                # Bases -> RELATES(inherits_from)
                bases = self._collect_class_bases(root, source_bytes, sym.name)
                for base_name in bases:
                    base_qualname = self._resolve_class_qualname(
                        base_name, module_qualname, root, source_bytes
                    )
                    base_id = f"{kb_name}::{base_qualname}"
                    if not self._has_node(nodes, base_id) and "__unresolved__" in base_qualname:
                        nodes.append(
                            GraphNode(
                                node_id=base_id,
                                label="Class",
                                properties={
                                    "kb_name": kb_name,
                                    "qualname": base_qualname,
                                    "name": base_name,
                                    "unresolved": True,
                                },
                            )
                        )
                    edges.append(
                        GraphEdge(
                            from_id=sym_id,
                            to_id=base_id,
                            rel_type="RELATES",
                            kind="inherits_from",
                        )
                    )

                # Methods inside the class
                for method in self._collect_methods(root, source_bytes, sym, module_qualname):
                    method_id = f"{kb_name}::{method.qualname}"
                    nodes.append(
                        GraphNode(
                            node_id=method_id,
                            label="Method",
                            properties={
                                "kb_name": kb_name,
                                "qualname": method.qualname,
                                "name": method.name,
                                "docstring": method.docstring or "",
                                "signature": method.signature,
                            },
                        )
                    )
                    edges.append(GraphEdge(from_id=sym_id, to_id=method_id, rel_type="CONTAINS"))
                    chunks.append(self._symbol_chunk(method, document_id, kb_name))

        return ParseResult(
            chunks=chunks,
            document=document_node,
            nodes=nodes,
            edges=edges,
        )

    # --- helpers ---
    def _derive_module_qualname(self, file_path: Path) -> str:
        """Walk package_roots to derive the dotted qualname.

        - file_path inside one of self._package_roots -> qualname = relative dotted path.
        - __init__.py -> use the parent dir's name (drop "__init__").
        - No matching package root -> use the file stem.
        """
        for root in self._package_roots:
            try:
                rel = file_path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            parts = list(rel.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts.pop()
            if parts:
                return ".".join(parts)
        return file_path.stem

    def _module_docstring(self, root: Node, src: bytes) -> str | None:
        """First string literal at module level is the module docstring."""
        for child in root.children:
            if child.type == "comment":
                continue
            if child.type == "expression_statement":
                for grand in child.children:
                    if grand.type == "string":
                        return self._strip_quotes(
                            src[grand.start_byte : grand.end_byte].decode(
                                "utf-8", errors="replace"
                            )
                        )
                return None
            return None
        return None

    def _strip_quotes(self, raw: str) -> str:
        # Tree-sitter "string" includes the triple-or-single quotes.
        for q in ('"""', "'''", '"', "'"):
            if raw.startswith(q) and raw.endswith(q) and len(raw) >= 2 * len(q):
                return raw[len(q) : -len(q)].strip()
        return raw.strip()

    def _collect_imports(self, root: Node, src: bytes) -> list[str]:
        """Return dotted module names for every import_statement / import_from_statement."""
        out: list[str] = []
        for child in root.children:
            if child.type == "import_statement":
                # `import a, b, c` and `import a.b as c`
                for n in child.named_children:
                    if n.type == "dotted_name":
                        out.append(src[n.start_byte : n.end_byte].decode())
                    elif n.type == "aliased_import":
                        for inner in n.named_children:
                            if inner.type == "dotted_name":
                                out.append(src[inner.start_byte : inner.end_byte].decode())
                                break
            elif child.type == "import_from_statement":
                # `from a.b import x, y`
                module_name_node = child.child_by_field_name("module_name")
                if module_name_node is not None:
                    out.append(
                        src[module_name_node.start_byte : module_name_node.end_byte].decode()
                    )
        return out

    def _resolve_module_id(self, target_qualname: str, kb_name: str) -> str:
        """If `target_qualname` is one of our packages -> first-party id; else placeholder."""
        for root in self._package_roots:
            parts = target_qualname.split(".")
            base = root.joinpath(*parts)
            if base.with_suffix(".py").exists() or (base / "__init__.py").exists():
                return f"{kb_name}::{target_qualname}"
        return f"{kb_name}::__external__::{target_qualname}"

    def _maybe_external_module(
        self, node_id: str, qualname: str, kb_name: str
    ) -> GraphNode | None:
        """Emit a placeholder Module node for unresolved imports."""
        if "__external__" not in node_id:
            return None
        return GraphNode(
            node_id=node_id,
            label="Module",
            properties={
                "kb_name": kb_name,
                "qualname": qualname,
                "name": qualname.rsplit(".", 1)[-1],
                "unresolved": True,
            },
        )

    def _collect_top_level_symbols(
        self, root: Node, src: bytes, module_qualname: str
    ) -> list[_Symbol]:
        """Top-level function_definition / class_definition / decorated_definition."""
        out: list[_Symbol] = []
        for child in root.children:
            sym = self._symbol_from_node(child, src, module_qualname, parent_qualname=None)
            if sym is not None:
                out.append(sym)
        return out

    def _symbol_from_node(
        self,
        node: Node,
        src: bytes,
        parent_module: str,
        *,
        parent_qualname: str | None,
    ) -> _Symbol | None:
        """Build a _Symbol from a function_definition or class_definition node."""
        # Unwrap `decorated_definition` -> its inner definition child.
        if node.type == "decorated_definition":
            for inner in node.named_children:
                if inner.type in ("function_definition", "class_definition"):
                    return self._symbol_from_node(
                        inner, src, parent_module, parent_qualname=parent_qualname
                    )
            return None

        if node.type not in ("function_definition", "class_definition"):
            return None
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = src[name_node.start_byte : name_node.end_byte].decode()
        kind = "class" if node.type == "class_definition" else "function"
        if kind == "function" and parent_qualname is not None:
            kind = "method"
        qualname_owner = parent_qualname if parent_qualname is not None else parent_module
        qualname = f"{qualname_owner}.{name}" if qualname_owner else name

        signature = self._signature_text(node, src)
        docstring = self._function_docstring(node, src)
        body_text = src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")[
            :_CHUNK_BODY_LIMIT
        ]
        return _Symbol(
            name=name,
            kind=kind,
            qualname=qualname,
            docstring=docstring,
            signature=signature,
            body_text=body_text,
            parent_qualname=parent_qualname,
        )

    def _signature_text(self, node: Node, src: bytes) -> str:
        """Take everything up to the body for a clean signature line."""
        body_node = node.child_by_field_name("body")
        end = body_node.start_byte if body_node is not None else node.end_byte
        return (
            src[node.start_byte : end]
            .decode("utf-8", errors="replace")
            .strip()
            .rstrip(":")
            .strip()
        )

    def _function_docstring(self, fn_node: Node, src: bytes) -> str | None:
        body = fn_node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.named_children:
            if child.type == "expression_statement":
                for grand in child.children:
                    if grand.type == "string":
                        return self._strip_quotes(
                            src[grand.start_byte : grand.end_byte].decode(
                                "utf-8", errors="replace"
                            )
                        )
                return None
            return None
        return None

    def _iter_class_definitions(self, root: Node) -> list[Node]:
        """Yield class_definition nodes at the module level (unwrapping decorators)."""
        out: list[Node] = []
        for child in root.children:
            inner = child
            if child.type == "decorated_definition":
                for c in child.named_children:
                    if c.type == "class_definition":
                        inner = c
                        break
            if inner.type == "class_definition":
                out.append(inner)
        return out

    def _collect_class_bases(self, root: Node, src: bytes, class_name: str) -> list[str]:
        """For ``class Derived(Base):`` return ``["Base"]``."""
        out: list[str] = []
        for inner in self._iter_class_definitions(root):
            name_node = inner.child_by_field_name("name")
            if name_node is None:
                continue
            if src[name_node.start_byte : name_node.end_byte].decode() != class_name:
                continue
            superclasses = inner.child_by_field_name("superclasses")
            if superclasses is None:
                return []
            for arg in superclasses.named_children:
                if arg.type in ("identifier", "attribute"):
                    out.append(src[arg.start_byte : arg.end_byte].decode())
        return out

    def _resolve_class_qualname(
        self, base_name: str, module_qualname: str, root: Node, src: bytes
    ) -> str:
        """If a class with `base_name` is defined in this same module, use its qualname.

        Otherwise: __unresolved__::<name> placeholder. Cross-module resolution is
        beyond PR-7 scope (deferred with calls).
        """
        for inner in self._iter_class_definitions(root):
            name_node = inner.child_by_field_name("name")
            if name_node is None:
                continue
            if src[name_node.start_byte : name_node.end_byte].decode() == base_name:
                if module_qualname:
                    return f"{module_qualname}.{base_name}"
                return base_name
        return f"__unresolved__::{base_name}"

    def _has_node(self, nodes: list[GraphNode], node_id: str) -> bool:
        return any(n.node_id == node_id for n in nodes)

    def _collect_methods(
        self, root: Node, src: bytes, class_sym: _Symbol, module_qualname: str
    ) -> list[_Symbol]:
        """Functions defined inside ``class_sym.qualname``."""
        out: list[_Symbol] = []
        for inner in self._iter_class_definitions(root):
            name_node = inner.child_by_field_name("name")
            if name_node is None:
                continue
            if src[name_node.start_byte : name_node.end_byte].decode() != class_sym.name:
                continue
            body = inner.child_by_field_name("body")
            if body is None:
                continue
            for body_child in body.named_children:
                method_sym = self._symbol_from_node(
                    body_child,
                    src,
                    module_qualname,
                    parent_qualname=class_sym.qualname,
                )
                if method_sym is not None:
                    out.append(method_sym)
        return out

    def _module_chunk(
        self,
        *,
        module_qualname: str,
        document_id: str,
        kb_name: str,
        docstring: str | None,
    ) -> Chunk:
        text = f"module {module_qualname}\n\n{docstring or ''}".strip()[:_CHUNK_BODY_LIMIT]
        return Chunk(
            content=text,
            file_path=document_id,
            header_breadcrumb=module_qualname,
            chunk_level=1,
            kind="code",
            language="python",
            artifact_qualname=f"{kb_name}::{module_qualname}",
            parent_document_id=document_id,
        )

    def _symbol_chunk(self, sym: _Symbol, document_id: str, kb_name: str) -> Chunk:
        text_parts = [sym.signature]
        if sym.docstring:
            text_parts.append(sym.docstring)
        if sym.body_text:
            text_parts.append(sym.body_text)
        return Chunk(
            content="\n\n".join(text_parts),
            file_path=document_id,
            header_breadcrumb=sym.qualname,
            chunk_level=2 if sym.kind != "method" else 3,
            kind="code",
            language="python",
            artifact_qualname=f"{kb_name}::{sym.qualname}",
            parent_document_id=document_id,
        )
