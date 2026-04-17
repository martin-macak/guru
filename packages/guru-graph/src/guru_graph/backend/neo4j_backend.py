"""Concrete GraphBackend using the official Neo4j Python driver over Bolt."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from ..neo4j_process import Neo4jRuntime, start_neo4j, stop_neo4j
from ..versioning import check_migration_target
from .base import BackendHealth, BackendInfo, CypherResult, GraphBackendRegistry, Tx

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


GraphBackendRegistry.register("neo4j", Neo4jBackend)
