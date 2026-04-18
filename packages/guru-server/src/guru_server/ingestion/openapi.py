"""OpenAPI 3.x parser (YAML + JSON).

Emits:
  (:Document)          — the spec file (anchors the file in the graph)
  (:OpenApiSpec)       — sub-artifact with version/title metadata
  (:OpenApiOperation)  — each paths.<path>.<method> entry
  (:OpenApiSchema)     — each components/schemas/<Name> entry

Plus CONTAINS edges:
  Document → OpenApiSpec
  OpenApiSpec → Operation
  OpenApiSpec → Schema

And RELATES{kind:"references"} edges for $ref usages (Operation → Schema,
Schema → Schema, including cross-file $ref to placeholder ids).

Out of scope per PR-8: actually parsing cross-file refs (we emit edges
to placeholder ids so future parses complete the graph). Circular refs
are handled via a visited set.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from guru_core.types import Rule
from guru_server.ingestion.base import (
    Chunk,
    DocumentParser,
    GraphEdge,
    GraphNode,
    ParseResult,
)

logger = logging.getLogger(__name__)

_HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
_COMBINATOR_KEYS = ("oneOf", "anyOf", "allOf")


class OpenApiParser(DocumentParser):
    @property
    def name(self) -> str:
        return "openapi"

    def supports(self, file_path: Path) -> bool:
        # Suffix-only — disambiguating OpenAPI vs arbitrary YAML/JSON without
        # a content peek would over-claim. Callers should match specific
        # filename patterns (e.g. ``**/openapi.{yaml,yml,json}``) if they
        # want to scope detection more tightly.
        return file_path.suffix.lower() in (".yaml", ".yml", ".json")

    def parse(
        self, file_path: Path, rule: Rule, *, kb_name: str, rel_path: str = ""
    ) -> ParseResult:
        if not rel_path:
            rel_path = file_path.name

        doc_id = f"{kb_name}::{rel_path}"
        spec_id = f"{kb_name}::{rel_path}::spec"
        language = "json" if file_path.suffix.lower() == ".json" else "yaml"

        # Load — tolerate parse errors gracefully.
        try:
            raw = file_path.read_text(encoding="utf-8")
            doc = yaml.safe_load(raw)
        except (OSError, yaml.YAMLError) as e:
            return self._malformed(doc_id, kb_name, rel_path, file_path, language, str(e))

        if not isinstance(doc, dict):
            return self._malformed(
                doc_id,
                kb_name,
                rel_path,
                file_path,
                language,
                "spec is not a YAML/JSON mapping",
            )

        # Not OpenAPI at all — still emit a Document so ingestion has something
        # to anchor to, but skip all the sub-artifact work.
        if "openapi" not in doc and "swagger" not in doc:
            return ParseResult(
                chunks=[],
                document=GraphNode(
                    node_id=doc_id,
                    label="Document",
                    properties=self._doc_properties(kb_name, rel_path, file_path, language)
                    | {"openapi": False},
                ),
                nodes=[],
                edges=[],
            )

        # Document node — satisfies IngestService.submit / upsert_document contract.
        doc_node = GraphNode(
            node_id=doc_id,
            label="Document",
            properties=self._doc_properties(kb_name, rel_path, file_path, language),
        )

        # OpenApiSpec sub-artifact — carries version/title metadata.
        spec_node = GraphNode(
            node_id=spec_id,
            label="OpenApiSpec",
            properties={
                "kb_name": kb_name,
                "openapi_version": str(doc.get("openapi") or doc.get("swagger") or "unknown"),
                "title": str((doc.get("info") or {}).get("title") or ""),
                "valid": True,
            },
        )

        nodes: list[GraphNode] = [spec_node]
        edges: list[GraphEdge] = [GraphEdge(from_id=doc_id, to_id=spec_id, rel_type="CONTAINS")]
        chunks: list[Chunk] = []

        # Operations — hang off the OpenApiSpec node.
        paths = doc.get("paths") or {}
        if isinstance(paths, dict):
            for path_str, path_item in paths.items():
                if not isinstance(path_item, dict):
                    continue
                for method, op in path_item.items():
                    if (
                        not isinstance(method, str)
                        or method.lower() not in _HTTP_METHODS
                        or not isinstance(op, dict)
                    ):
                        continue
                    method_lower = method.lower()
                    op_qualname = f"{rel_path}::{path_str}::{method_lower}"
                    op_node_id = f"{kb_name}::{op_qualname}"
                    op_node = GraphNode(
                        node_id=op_node_id,
                        label="OpenApiOperation",
                        properties={
                            "kb_name": kb_name,
                            "qualname": op_qualname,
                            "path": path_str,
                            "method": method_lower,
                            "operation_id": str(op.get("operationId") or ""),
                            "summary": str(op.get("summary") or ""),
                        },
                    )
                    nodes.append(op_node)
                    edges.append(GraphEdge(from_id=spec_id, to_id=op_node_id, rel_type="CONTAINS"))
                    chunks.append(
                        self._operation_chunk(
                            op_node_id=op_node_id,
                            doc_id=doc_id,
                            path=path_str,
                            method=method_lower,
                            op=op,
                            language=language,
                        )
                    )
                    for ref in self._collect_refs(op):
                        edges.extend(
                            self._ref_to_edges(
                                from_id=op_node_id,
                                ref=ref,
                                kb_name=kb_name,
                                file_dir=file_path.parent,
                                base_rel_path=rel_path,
                                placeholders=nodes,
                            )
                        )

        # Schemas — hang off the OpenApiSpec node.
        components = doc.get("components") or {}
        schemas = (components.get("schemas") or {}) if isinstance(components, dict) else {}
        if isinstance(schemas, dict):
            for name, schema in schemas.items():
                schema_qualname = f"{rel_path}::components/schemas/{name}"
                schema_node_id = f"{kb_name}::{schema_qualname}"
                shape = self._detect_shape(schema)
                schema_node = GraphNode(
                    node_id=schema_node_id,
                    label="OpenApiSchema",
                    properties={
                        "kb_name": kb_name,
                        "qualname": schema_qualname,
                        "name": name,
                        "type": (
                            str(schema.get("type") or "") if isinstance(schema, dict) else ""
                        ),
                        "shape": shape,
                    },
                )
                nodes.append(schema_node)
                edges.append(GraphEdge(from_id=spec_id, to_id=schema_node_id, rel_type="CONTAINS"))
                chunks.append(
                    self._schema_chunk(
                        schema_node_id=schema_node_id,
                        doc_id=doc_id,
                        name=name,
                        schema=schema,
                        language=language,
                    )
                )
                if isinstance(schema, dict):
                    for ref in self._collect_refs(schema):
                        edges.extend(
                            self._ref_to_edges(
                                from_id=schema_node_id,
                                ref=ref,
                                kb_name=kb_name,
                                file_dir=file_path.parent,
                                base_rel_path=rel_path,
                                placeholders=nodes,
                            )
                        )

        return ParseResult(chunks=chunks, document=doc_node, nodes=nodes, edges=edges)

    # --- helpers ---

    def _doc_properties(
        self, kb_name: str, rel_path: str, file_path: Path, language: str
    ) -> dict[str, Any]:
        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = 0
        return {
            "kb_name": kb_name,
            "relative_path": rel_path,
            "absolute_path": str(file_path),
            "language": language,
            "file_type": "schema",
            "parser_name": "openapi",
            "size_bytes": size_bytes,
        }

    def _malformed(
        self,
        doc_id: str,
        kb_name: str,
        rel_path: str,
        file_path: Path,
        language: str,
        error: str,
    ) -> ParseResult:
        """Single Document node with valid=False; no sub-artifacts.

        IngestService will still index the file and submit a (:Document) node
        to the graph; the agent can ``graph_describe`` it and see the error.
        """
        document = GraphNode(
            node_id=doc_id,
            label="Document",
            properties=self._doc_properties(kb_name, rel_path, file_path, language)
            | {
                "valid": False,
                "error": error,
            },
        )
        return ParseResult(chunks=[], document=document, nodes=[], edges=[])

    def _operation_chunk(
        self,
        *,
        op_node_id: str,
        doc_id: str,
        path: str,
        method: str,
        op: dict,
        language: str,
    ) -> Chunk:
        body_dict = {"path": path, "method": method, **op}
        body_text = yaml.safe_dump(body_dict, sort_keys=False)
        return Chunk(
            content=body_text,
            file_path=doc_id,
            header_breadcrumb=f"{method.upper()} {path}",
            chunk_level=2,
            kind="openapi_operation",
            language=language,
            artifact_qualname=op_node_id,
            parent_document_id=doc_id,
        )

    def _schema_chunk(
        self,
        *,
        schema_node_id: str,
        doc_id: str,
        name: str,
        schema: Any,
        language: str,
    ) -> Chunk:
        body_text = yaml.safe_dump({name: schema}, sort_keys=False)
        return Chunk(
            content=body_text,
            file_path=doc_id,
            header_breadcrumb=f"schemas/{name}",
            chunk_level=2,
            kind="openapi_schema",
            language=language,
            artifact_qualname=schema_node_id,
            parent_document_id=doc_id,
        )

    def _detect_shape(self, schema: Any) -> str:
        if not isinstance(schema, dict):
            return "scalar"
        for k in _COMBINATOR_KEYS:
            if k in schema:
                return k
        return str(schema.get("type") or "object")

    def _collect_refs(self, obj: Any, *, visited: set[int] | None = None) -> list[str]:
        """Recursively collect every ``$ref`` string in a nested dict/list.

        ``visited`` is keyed by ``id(obj)`` so YAML anchors (which produce
        shared-identity sub-trees) don't cause infinite recursion. Note the
        distinction from the node-id visited set in ``_ref_to_edges`` — this
        one guards against recursion in the parsed document structure itself.
        """
        if visited is None:
            visited = set()
        out: list[str] = []
        oid = id(obj)
        if oid in visited:
            return out
        visited.add(oid)
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "$ref" and isinstance(v, str):
                    out.append(v)
                else:
                    out.extend(self._collect_refs(v, visited=visited))
        elif isinstance(obj, list):
            for v in obj:
                out.extend(self._collect_refs(v, visited=visited))
        return out

    def _ref_to_edges(
        self,
        *,
        from_id: str,
        ref: str,
        kb_name: str,
        file_dir: Path,
        base_rel_path: str,
        placeholders: list[GraphNode],
    ) -> list[GraphEdge]:
        """Translate one ``$ref`` string into a list of edges (typically one).

        Local refs (``#/components/schemas/Foo``) → edge to the in-doc schema
        node. Cross-file refs (``./shared.yaml#/components/schemas/X``) →
        edge to a placeholder node id, plus a placeholder :OpenApiSchema node
        if the target file doesn't exist on disk.
        """
        if ref.startswith("#/"):
            inner = ref[2:]
            target_id = f"{kb_name}::{base_rel_path}::{inner}"
            return [
                GraphEdge(
                    from_id=from_id,
                    to_id=target_id,
                    rel_type="RELATES",
                    kind="references",
                )
            ]

        # Cross-file ref: split on "#"
        if "#" in ref:
            file_part, fragment = ref.split("#", 1)
        else:
            file_part, fragment = ref, ""

        try:
            target_path = (file_dir / file_part).resolve()
        except OSError:
            target_path = file_dir / file_part

        # Build a reasonable rel-path-style id for the cross-file target.
        cross_rel = self._cross_ref_relpath(file_dir, target_path, base_rel_path, file_part)
        fragment_part = fragment.lstrip("/")
        target_id = (
            f"{kb_name}::{cross_rel}::{fragment_part}"
            if fragment_part
            else f"{kb_name}::{cross_rel}"
        )

        if not target_path.exists() and not any(n.node_id == target_id for n in placeholders):
            placeholders.append(
                GraphNode(
                    node_id=target_id,
                    label="OpenApiSchema",
                    properties={
                        "kb_name": kb_name,
                        "qualname": target_id.split("::", 1)[1],
                        "unresolved": True,
                    },
                )
            )
        return [
            GraphEdge(
                from_id=from_id,
                to_id=target_id,
                rel_type="RELATES",
                kind="references",
            )
        ]

    def _cross_ref_relpath(
        self, file_dir: Path, target_path: Path, base_rel_path: str, file_part: str
    ) -> str:
        """Best-effort relative path for a cross-file ref target.

        We don't know the KB root from inside the parser, so we approximate by
        resolving target_path against file_dir and joining with the base rel
        path's parent. If that fails we fall back to the raw file_part string
        (which is likely fine for IDs anyway — the edge just has to be stable).
        """
        # Anchor to the parent of the spec's rel_path when possible.
        base_parent = Path(base_rel_path).parent
        try:
            resolved_dir = file_dir.resolve()
        except OSError:
            resolved_dir = file_dir
        try:
            rel = target_path.relative_to(resolved_dir)
            joined = base_parent / rel
            return joined.as_posix().lstrip("./")
        except ValueError:
            pass
        # Fallback: just combine base_parent with the raw file_part string.
        joined = base_parent / file_part
        return joined.as_posix().lstrip("./")
