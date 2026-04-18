"""Concrete GraphBackend using the official Neo4j Python driver over Bolt."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from ..neo4j_process import Neo4jRuntime, start_neo4j, stop_neo4j
from ..versioning import check_migration_target
from .base import (
    ALLOWED_ARTIFACT_LABELS,
    BackendHealth,
    BackendInfo,
    CypherResult,
    GraphBackendRegistry,
    Tx,
)

logger = logging.getLogger(__name__)


class _Neo4jTx(Tx):
    """Transaction handle backed by an open Neo4j driver transaction.

    Overrides :meth:`execute` and :meth:`execute_read` to run queries on the
    already-opened ``neo4j_tx`` instead of opening a new session, so
    transactional semantics are actually honoured.
    """

    def __init__(self, *, neo4j_tx, read_only: bool = False) -> None:
        # Pass a dummy backend — _Neo4jTx overrides execute/execute_read so the
        # base class's backend dispatch is never reached.
        super().__init__(backend=None, read_only=read_only)  # type: ignore[arg-type]
        self._neo4j_tx = neo4j_tx

    def execute(self, cypher: str, params: dict | None = None) -> CypherResult:
        return self._run(cypher, params or {})

    def execute_read(self, cypher: str, params: dict | None = None) -> CypherResult:
        return self._run(cypher, params or {})

    def _run(self, cypher: str, params: dict) -> CypherResult:
        start = time.monotonic()
        res = self._neo4j_tx.run(cypher, parameters=params)
        columns = list(res.keys())
        rows = [list(r.values()) for r in res]
        elapsed_ms = (time.monotonic() - start) * 1000
        return CypherResult(columns=columns, rows=rows, elapsed_ms=elapsed_ms)


class Neo4jBackend:
    """Owns a Bolt driver pointed at Neo4j.

    Two modes:
    - **subprocess mode** (default): ``bolt_uri`` is None. ``start()`` spawns
      ``neo4j console`` as a child process under our control (requires a
      ``neo4j`` binary on PATH and a writable conf dir).
    - **connect-only mode**: ``bolt_uri`` is set. ``start()`` connects to an
      already-running Neo4j at that URI and never touches a subprocess. This
      is what CI uses with its ``neo4j:5`` service container and what any
      docker-based local-dev setup should use.
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        bolt_port: int,
        log_file: Path,
        bolt_uri: str | None = None,
    ):
        if bolt_uri is not None and not bolt_uri.startswith(("bolt://", "neo4j://")):
            raise ValueError(f"bolt_uri must start with 'bolt://' or 'neo4j://', got {bolt_uri!r}")
        self._data_dir = data_dir
        self._bolt_port = bolt_port
        self._log_file = log_file
        self._external_bolt_uri = bolt_uri
        self._runtime: Neo4jRuntime | None = None
        self._driver = None
        self._schema_version = 0
        self._neo4j_version = "unknown"

    # ---- Lifecycle ----
    def start(self) -> None:
        if self._external_bolt_uri is not None:
            logger.info("connect-only mode: using external Neo4j at %s", self._external_bolt_uri)
            bolt_uri = self._external_bolt_uri
        else:
            self._runtime = start_neo4j(
                data_dir=self._data_dir,
                bolt_port=self._bolt_port,
                log_file=self._log_file,
            )
            bolt_uri = self._runtime.bolt_uri
        self._driver = GraphDatabase.driver(bolt_uri, auth=None)
        try:
            with self._driver.session() as s:
                rec = s.run(
                    "CALL dbms.components() YIELD name, versions "
                    "WHERE name='Neo4j Kernel' RETURN versions[0] AS v"
                ).single()
                if rec:
                    self._neo4j_version = rec["v"]
        except Exception as e:
            logger.warning("could not read neo4j version: %s", e)
        self._schema_version = self._read_schema_version()

    def stop(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
        if self._runtime is not None:
            stop_neo4j(self._runtime.process)
            self._runtime = None

    # ---- Health + info ----
    def health(self) -> BackendHealth:
        if self._driver is None:
            return BackendHealth(healthy=False, detail="driver not initialised")
        try:
            self._driver.verify_connectivity()
            return BackendHealth(healthy=True)
        except Exception as e:
            return BackendHealth(healthy=False, detail=str(e))

    def info(self) -> BackendInfo:
        return BackendInfo(
            name="neo4j",
            version=self._neo4j_version,
            schema_version=self._schema_version,
        )

    # ---- Cypher surface ----
    def execute(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        assert self._driver is not None
        start = time.monotonic()
        with self._driver.session() as s:
            res = s.run(cypher, parameters=params)
            columns = list(res.keys())
            rows = [list(r.values()) for r in res]
        elapsed_ms = (time.monotonic() - start) * 1000
        return CypherResult(columns=columns, rows=rows, elapsed_ms=elapsed_ms)

    def execute_read(self, cypher: str, params: dict[str, Any]) -> CypherResult:
        assert self._driver is not None
        start = time.monotonic()
        with self._driver.session() as s:

            def _work(tx):
                res = tx.run(cypher, parameters=params)
                return list(res.keys()), [list(r.values()) for r in res]

            columns, rows = s.execute_read(_work)
        elapsed_ms = (time.monotonic() - start) * 1000
        return CypherResult(columns=columns, rows=rows, elapsed_ms=elapsed_ms)

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[Tx]:
        assert self._driver is not None
        with self._driver.session() as s:
            neo4j_tx = s.begin_transaction()
            tx = _Neo4jTx(neo4j_tx=neo4j_tx, read_only=read_only)
            try:
                yield tx
                neo4j_tx.commit()
            except Exception:
                neo4j_tx.rollback()
                raise

    # ---- Schema ----
    def ensure_schema(self, target_version: int) -> None:
        current = self._read_schema_version()
        check_migration_target(current=current, target=target_version)
        from ..migrations import run_pending_migrations

        run_pending_migrations(backend=self, current=current, target=target_version)
        self._schema_version = self._read_schema_version()

    def _read_schema_version(self) -> int:
        if self._driver is None:
            return 0
        with self._driver.session() as s:
            rec = s.run("MATCH (m:_Meta {kind: 'schema'}) RETURN m.schema_version AS v").single()
            return int(rec["v"]) if rec and rec["v"] is not None else 0

    # ---- Declarative KB helpers (called by KbService) ----
    def upsert_kb(
        self, *, name: str, project_root: str, tags: list[str], metadata_json: str
    ) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MERGE (k:Kb {name: $name})
                ON CREATE SET k.created_at = timestamp(), k.updated_at = timestamp(),
                              k.project_root = $project_root,
                              k.tags = $tags,
                              k.metadata_json = $metadata_json
                ON MATCH SET k.updated_at = timestamp(),
                             k.project_root = $project_root,
                             k.tags = $tags,
                             k.metadata_json = $metadata_json
                """,
                parameters={
                    "name": name,
                    "project_root": project_root,
                    "tags": tags,
                    "metadata_json": metadata_json,
                },
            )

    def get_kb(self, name: str) -> dict[str, Any] | None:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (k:Kb {name: $name}) "
                "RETURN k.name AS name, k.project_root AS project_root, "
                "       k.tags AS tags, k.metadata_json AS metadata_json, "
                "       k.created_at AS created_at, k.updated_at AS updated_at",
                parameters={"name": name},
            ).single()
            if rec is None:
                return None
            return {
                "name": rec["name"],
                "project_root": rec["project_root"],
                "tags": list(rec["tags"] or []),
                "metadata_json": rec["metadata_json"] or "{}",
                "created_at": rec["created_at"] / 1000.0,
                "updated_at": rec["updated_at"] / 1000.0,
            }

    def list_kbs(
        self, *, prefix: str | None = None, tag: str | None = None
    ) -> list[dict[str, Any]]:
        filters = []
        params: dict[str, Any] = {}
        if prefix:
            filters.append("k.name STARTS WITH $prefix")
            params["prefix"] = prefix
        if tag:
            filters.append("$tag IN k.tags")
            params["tag"] = tag
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cypher = (
            f"MATCH (k:Kb) {where} "
            "RETURN k.name AS name, k.project_root AS project_root, "
            "       k.tags AS tags, k.metadata_json AS metadata_json, "
            "       k.created_at AS created_at, k.updated_at AS updated_at "
            "ORDER BY k.name"
        )
        with self._driver.session() as s:
            rs = s.run(cypher, parameters=params)
            return [
                {
                    "name": r["name"],
                    "project_root": r["project_root"],
                    "tags": list(r["tags"] or []),
                    "metadata_json": r["metadata_json"] or "{}",
                    "created_at": r["created_at"] / 1000.0,
                    "updated_at": r["updated_at"] / 1000.0,
                }
                for r in rs
            ]

    def delete_kb(self, name: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (k:Kb {name: $name}) "
                "OPTIONAL MATCH (k)-[r:LINKS]-() "
                "WITH k, count(r) AS edges DELETE r, k RETURN edges + 1 AS deleted",
                parameters={"name": name},
            ).single()
            return bool(rec and rec["deleted"])

    def link(self, *, from_kb: str, to_kb: str, kind: str, metadata_json: str) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MATCH (a:Kb {name: $from_kb}), (b:Kb {name: $to_kb})
                MERGE (a)-[r:LINKS {kind: $kind}]->(b)
                ON CREATE SET r.created_at = timestamp(),
                              r.metadata_json = $metadata_json
                ON MATCH SET r.metadata_json = $metadata_json
                """,
                parameters={
                    "from_kb": from_kb,
                    "to_kb": to_kb,
                    "kind": kind,
                    "metadata_json": metadata_json,
                },
            )

    def unlink(self, *, from_kb: str, to_kb: str, kind: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (a:Kb {name: $from_kb})-[r:LINKS {kind: $kind}]->(b:Kb {name: $to_kb})
                WITH r, count(r) AS c DELETE r RETURN c
                """,
                parameters={"from_kb": from_kb, "to_kb": to_kb, "kind": kind},
            ).single()
            return bool(rec and rec["c"])

    def list_links_for(self, *, name: str, direction: str = "both") -> list[dict[str, Any]]:
        if direction == "out":
            cypher = (
                "MATCH (a:Kb {name: $name})-[r:LINKS]->(b:Kb) "
                "RETURN a.name AS from_kb, b.name AS to_kb, r.kind AS kind, "
                "       r.created_at AS created_at, r.metadata_json AS metadata_json"
            )
        elif direction == "in":
            cypher = (
                "MATCH (a:Kb)-[r:LINKS]->(b:Kb {name: $name}) "
                "RETURN a.name AS from_kb, b.name AS to_kb, r.kind AS kind, "
                "       r.created_at AS created_at, r.metadata_json AS metadata_json"
            )
        else:
            cypher = (
                "MATCH (a:Kb)-[r:LINKS]->(b:Kb) "
                "WHERE a.name = $name OR b.name = $name "
                "RETURN a.name AS from_kb, b.name AS to_kb, r.kind AS kind, "
                "       r.created_at AS created_at, r.metadata_json AS metadata_json"
            )
        with self._driver.session() as s:
            rs = s.run(cypher, parameters={"name": name})
            return [
                {
                    "from_kb": r["from_kb"],
                    "to_kb": r["to_kb"],
                    "kind": r["kind"],
                    "created_at": r["created_at"] / 1000.0,
                    "metadata_json": r["metadata_json"] or "{}",
                }
                for r in rs
            ]

    # ---- Declarative artifact helpers (called by artifact services) ----
    def upsert_document(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None:
        assert label == "Document", f"upsert_document requires label='Document', got {label!r}"
        with self._driver.session() as s:
            s.run(
                """
                MERGE (d:Document {id: $id})
                ON CREATE SET d.created_at = timestamp()
                SET d += $props
                SET d.updated_at = timestamp()
                """,
                parameters={"id": node_id, "props": dict(properties)},
            )

    def upsert_artifact(self, *, node_id: str, label: str, properties: dict[str, Any]) -> None:
        if label == "Document":
            self.upsert_document(node_id=node_id, label=label, properties=properties)
            return
        if label not in ALLOWED_ARTIFACT_LABELS:
            raise ValueError(f"unknown artifact label: {label!r}")
        # Label is from our allow-list, so f-string substitution is safe.
        cypher = (
            f"MERGE (n:{label} {{id: $id}}) "
            "ON CREATE SET n.created_at = timestamp() "
            "SET n += $props "
            "SET n.updated_at = timestamp()"
        )
        with self._driver.session() as s:
            s.run(cypher, parameters={"id": node_id, "props": dict(properties)})

    def delete_artifact(self, *, node_id: str) -> None:
        with self._driver.session() as s:
            s.run(
                "MATCH (n {id: $id}) DETACH DELETE n",
                parameters={"id": node_id},
            )

    def delete_artifact_with_descendants(self, *, node_id: str) -> list[str]:
        """See :meth:`ArtifactOpsBackend.delete_artifact_with_descendants`."""
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (r {id: $id})
                OPTIONAL MATCH (r)-[:CONTAINS*0..]->(c)
                WITH collect(DISTINCT c.id) AS child_ids, r
                WITH [r.id] + [x IN child_ids WHERE x IS NOT NULL] AS all_ids
                RETURN all_ids
                """,
                parameters={"id": node_id},
            ).single()
            if rec is None or rec["all_ids"] is None:
                return []
            # Deduplicate in order (root may also appear in child_ids).
            seen: set[str] = set()
            out: list[str] = []
            for x in rec["all_ids"]:
                if x is None or x in seen:
                    continue
                seen.add(x)
                out.append(x)
            return out

    def create_contains_edge(self, *, from_id: str, to_id: str) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MATCH (a {id: $from}), (b {id: $to})
                MERGE (a)-[:CONTAINS]->(b)
                """,
                parameters={"from": from_id, "to": to_id},
            )

    def create_relates_edge(
        self, *, from_id: str, to_id: str, kind: str, properties: dict[str, Any]
    ) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MATCH (a {id: $from}), (b {id: $to})
                MERGE (a)-[r:RELATES {kind: $kind}]->(b)
                ON CREATE SET r.created_at = timestamp()
                SET r += $props
                SET r.updated_at = timestamp()
                """,
                parameters={
                    "from": from_id,
                    "to": to_id,
                    "kind": kind,
                    "props": dict(properties),
                },
            )

    def delete_relates_edge(self, *, from_id: str, to_id: str, kind: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (a {id: $from})-[r:RELATES {kind: $kind}]->(b {id: $to})
                WITH r, count(r) AS c DELETE r RETURN c
                """,
                parameters={"from": from_id, "to": to_id, "kind": kind},
            ).single()
            return bool(rec and rec["c"])

    def remove_outbound_relates_rooted_at(self, *, doc_id: str) -> None:
        with self._driver.session() as s:
            s.run(
                """
                MATCH (d:Document {id: $id})-[:CONTAINS*0..]->(n)
                OPTIONAL MATCH (n)-[r:RELATES]->()
                DELETE r
                """,
                parameters={"id": doc_id},
            )

    def get_document_snapshot(self, *, doc_id: str) -> list[str]:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (d:Document {id: $id}) RETURN d.snapshot_ids_json AS s",
                parameters={"id": doc_id},
            ).single()
            if rec is None or rec["s"] is None:
                return []
            try:
                parsed = json.loads(rec["s"])
            except (ValueError, TypeError):
                return []
            return list(parsed) if isinstance(parsed, list) else []

    def set_document_snapshot(self, *, doc_id: str, node_ids: list[str]) -> None:
        with self._driver.session() as s:
            s.run(
                "MATCH (d:Document {id: $id}) SET d.snapshot_ids_json = $json",
                parameters={"id": doc_id, "json": json.dumps(list(node_ids))},
            )

    def orphan_annotations_for(self, *, node_ids: list[str]) -> None:
        if not node_ids:
            return
        with self.transaction() as tx:
            tx.execute(
                "MATCH (a:Annotation)-[:ANNOTATES]->(t) WHERE t.id IN $ids "
                "SET a.updated_at = timestamp()",
                {"ids": list(node_ids)},
            )
            tx.execute(
                "MATCH (a:Annotation)-[r:ANNOTATES]->(t) WHERE t.id IN $ids DELETE r",
                {"ids": list(node_ids)},
            )

    def get_artifact(self, *, node_id: str) -> dict[str, Any] | None:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (n {id: $id}) RETURN labels(n) AS labels, properties(n) AS props",
                parameters={"id": node_id},
            ).single()
            if rec is None:
                return None
            labels = [lbl for lbl in (rec["labels"] or []) if not lbl.startswith("_")]
            if not labels:
                return None
            return {
                "id": node_id,
                "label": labels[0],
                "properties": dict(rec["props"] or {}),
            }

    def list_neighbors(
        self,
        *,
        node_id: str,
        direction: str,
        rel_type: str,
        kind: str | None,
        depth: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        # TODO(PR-4): implement multi-hop + kind filter semantics.
        # For now, support depth=1 only; if depth > 1 the caller is truncated
        # with a warning (callers in PR-4/PR-6 will evolve this).
        if depth > 1:
            logger.warning("list_neighbors: depth>1 not yet supported; truncating to depth=1")
        if direction == "out":
            pattern = "(n {id: $id})-[r]->(m)"
        elif direction == "in":
            pattern = "(n {id: $id})<-[r]-(m)"
        else:
            pattern = "(n {id: $id})-[r]-(m)"
        if rel_type == "both":
            types_clause = "WHERE type(r) IN ['CONTAINS','RELATES']"
        elif rel_type in ("CONTAINS", "RELATES"):
            types_clause = f"WHERE type(r) = '{rel_type}'"
        else:
            types_clause = "WHERE type(r) IN ['CONTAINS','RELATES']"
        if kind is not None:
            types_clause += " AND (type(r) <> 'RELATES' OR r.kind = $kind)"
        cypher = (
            f"MATCH {pattern} {types_clause} "
            "RETURN m.id AS id, labels(m)[0] AS label, type(r) AS rel_type, "
            "       r.kind AS kind, 1 AS distance "
            "LIMIT $limit"
        )
        params: dict[str, Any] = {"id": node_id, "limit": limit}
        if kind is not None:
            params["kind"] = kind
        with self._driver.session() as s:
            rs = s.run(cypher, parameters=params)
            return [
                {
                    "id": r["id"],
                    "label": r["label"],
                    "rel_type": r["rel_type"],
                    "kind": r["kind"],
                    "distance": r["distance"],
                }
                for r in rs
            ]

    def find_artifacts(
        self,
        *,
        name: str | None,
        qualname_prefix: str | None,
        label: str | None,
        tag: str | None,
        kb_name: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if label is not None:
            if label != "Document" and label not in ALLOWED_ARTIFACT_LABELS:
                raise ValueError(f"unknown artifact label: {label!r}")
            match_clause = f"MATCH (n:{label})"
        else:
            match_clause = "MATCH (n)"
        filters: list[str] = []
        if name is not None:
            filters.append("n.name = $name")
            params["name"] = name
        if qualname_prefix is not None:
            filters.append("n.qualname STARTS WITH $qualname_prefix")
            params["qualname_prefix"] = qualname_prefix
        if tag is not None:
            filters.append("$tag IN n.tags")
            params["tag"] = tag
        if kb_name is not None:
            filters.append("n.kb_name = $kb_name")
            params["kb_name"] = kb_name
        # Always filter out schema/meta nodes.
        filters.append("NOT any(lbl IN labels(n) WHERE lbl STARTS WITH '_')")
        where = "WHERE " + " AND ".join(filters)
        cypher = (
            f"{match_clause} {where} "
            "RETURN n.id AS id, labels(n) AS labels, properties(n) AS props "
            "LIMIT $limit"
        )
        with self._driver.session() as s:
            rs = s.run(cypher, parameters=params)
            out: list[dict[str, Any]] = []
            for r in rs:
                labels = [lbl for lbl in (r["labels"] or []) if not lbl.startswith("_")]
                if not labels:
                    continue
                out.append(
                    {
                        "id": r["id"],
                        "label": labels[0],
                        "properties": dict(r["props"] or {}),
                    }
                )
            return out

    def list_annotations_for(self, *, node_id: str) -> list[dict[str, Any]]:
        with self._driver.session() as s:
            rs = s.run(
                """
                MATCH (a:Annotation)-[:ANNOTATES]->(t {id: $id})
                RETURN a.id AS annotation_id, t.id AS target_id, labels(t)[0] AS target_label,
                       a.kind AS kind, a.body AS body, a.tags AS tags, a.author AS author,
                       a.created_at AS created_at, a.updated_at AS updated_at,
                       a.target_snapshot_json AS target_snapshot_json
                """,
                parameters={"id": node_id},
            )
            return [_annotation_row_to_dict(r) for r in rs]

    def list_relates_for(self, *, node_id: str, direction: str) -> list[dict[str, Any]]:
        if direction == "out":
            cypher = (
                "MATCH (a {id: $id})-[r:RELATES]->(b) "
                "RETURN a.id AS from_id, b.id AS to_id, r.kind AS kind, "
                "       properties(r) AS props"
            )
        elif direction == "in":
            cypher = (
                "MATCH (a)-[r:RELATES]->(b {id: $id}) "
                "RETURN a.id AS from_id, b.id AS to_id, r.kind AS kind, "
                "       properties(r) AS props"
            )
        else:
            cypher = (
                "MATCH (a)-[r:RELATES]->(b) "
                "WHERE a.id = $id OR b.id = $id "
                "RETURN a.id AS from_id, b.id AS to_id, r.kind AS kind, "
                "       properties(r) AS props"
            )
        with self._driver.session() as s:
            rs = s.run(cypher, parameters={"id": node_id})
            return [
                {
                    "from_id": r["from_id"],
                    "to_id": r["to_id"],
                    "kind": r["kind"],
                    "properties": dict(r["props"] or {}),
                }
                for r in rs
            ]

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
    ) -> dict[str, Any]:
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (t {id: $target_id})
                CREATE (a:Annotation {
                    id: $annotation_id,
                    kind: $kind,
                    body: $body,
                    tags: $tags,
                    author: $author,
                    target_snapshot_json: $snap,
                    created_at: timestamp(),
                    updated_at: timestamp()
                })
                CREATE (a)-[:ANNOTATES]->(t)
                RETURN a.id AS annotation_id, t.id AS target_id, labels(t)[0] AS target_label,
                       a.kind AS kind, a.body AS body, a.tags AS tags, a.author AS author,
                       a.created_at AS created_at, a.updated_at AS updated_at,
                       a.target_snapshot_json AS target_snapshot_json
                """,
                parameters={
                    "annotation_id": annotation_id,
                    "target_id": target_id,
                    "kind": kind,
                    "body": body,
                    "tags": list(tags),
                    "author": author,
                    "snap": target_snapshot_json,
                },
            ).single()
            if rec is None:
                raise KeyError(f"target {target_id!r} not found")
            return _annotation_row_to_dict(rec)

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
    ) -> dict[str, Any]:
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (t {id: $target_id})
                MERGE (a:Annotation {id: $annotation_id})
                ON CREATE SET a.kind = 'summary', a.body = $body, a.tags = $tags,
                              a.author = $author, a.target_snapshot_json = $snap,
                              a.created_at = timestamp(), a.updated_at = timestamp()
                ON MATCH SET a.kind = 'summary', a.body = $body, a.tags = $tags,
                             a.author = $author, a.target_snapshot_json = $snap,
                             a.updated_at = timestamp()
                MERGE (a)-[:ANNOTATES]->(t)
                RETURN a.id AS annotation_id, t.id AS target_id, labels(t)[0] AS target_label,
                       a.kind AS kind, a.body AS body, a.tags AS tags, a.author AS author,
                       a.created_at AS created_at, a.updated_at AS updated_at,
                       a.target_snapshot_json AS target_snapshot_json
                """,
                parameters={
                    "annotation_id": annotation_id,
                    "target_id": target_id,
                    "body": body,
                    "tags": list(tags),
                    "author": author,
                    "snap": target_snapshot_json,
                },
            ).single()
            if rec is None:
                raise KeyError(f"target {target_id!r} not found")
            return _annotation_row_to_dict(rec)

    def delete_annotation(self, *, annotation_id: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (a:Annotation {id: $id})
                WITH a, count(a) AS c DETACH DELETE a RETURN c
                """,
                parameters={"id": annotation_id},
            ).single()
            return bool(rec and rec["c"])

    def get_annotation(self, *, annotation_id: str) -> dict[str, Any] | None:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (a:Annotation {id: $id}) "
                "OPTIONAL MATCH (a)-[:ANNOTATES]->(t) "
                "RETURN a.id AS annotation_id, "
                "       t.id AS target_id, "
                "       labels(t)[0] AS target_label, "
                "       a.kind AS kind, a.body AS body, a.tags AS tags, "
                "       a.author AS author, "
                "       a.created_at AS created_at, a.updated_at AS updated_at, "
                "       a.target_snapshot_json AS target_snapshot_json",
                parameters={"id": annotation_id},
            ).single()
            if rec is None:
                return None
            return _annotation_row_to_dict(rec)

    def list_orphans(self, *, limit: int) -> list[dict[str, Any]]:
        with self._driver.session() as s:
            rs = s.run(
                """
                MATCH (a:Annotation)
                WHERE NOT (a)-[:ANNOTATES]->()
                RETURN a.id AS annotation_id, NULL AS target_id, NULL AS target_label,
                       a.kind AS kind, a.body AS body, a.tags AS tags, a.author AS author,
                       a.created_at AS created_at, a.updated_at AS updated_at,
                       a.target_snapshot_json AS target_snapshot_json
                LIMIT $limit
                """,
                parameters={"limit": limit},
            )
            return [_annotation_row_to_dict(r) for r in rs]

    def reattach_orphan(self, *, annotation_id: str, new_target_id: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                """
                MATCH (a:Annotation {id: $aid})
                WHERE NOT (a)-[:ANNOTATES]->()
                MATCH (t {id: $tid})
                MERGE (a)-[:ANNOTATES]->(t)
                SET a.updated_at = timestamp()
                RETURN count(t) AS c
                """,
                parameters={"aid": annotation_id, "tid": new_target_id},
            ).single()
            return bool(rec and rec["c"])


def _annotation_row_to_dict(rec) -> dict[str, Any]:
    created = rec["created_at"]
    updated = rec["updated_at"]
    return {
        "annotation_id": rec["annotation_id"],
        "target_id": rec["target_id"],
        "target_label": rec["target_label"],
        "kind": rec["kind"],
        "body": rec["body"],
        "tags": list(rec["tags"] or []),
        "author": rec["author"],
        "created_at": created / 1000.0 if created is not None else None,
        "updated_at": updated / 1000.0 if updated is not None else None,
        "target_snapshot_json": rec["target_snapshot_json"],
    }


GraphBackendRegistry.register("neo4j", Neo4jBackend)
