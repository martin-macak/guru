from __future__ import annotations

import json
import logging

import lancedb

from guru_server.ingestion.base import Chunk

logger = logging.getLogger(__name__)

VECTOR_DIM = 768
TABLE_NAME = "chunks"

_TABLE_NOT_FOUND_PHRASES = ("not found", "does not exist", "no such", "notfounderror")


class VectorStore:
    def __init__(self, db_path: str):
        self.db = lancedb.connect(db_path)
        self._table = None

    def _get_table(self):
        if self._table is None:
            try:
                self._table = self.db.open_table(TABLE_NAME)
            except FileNotFoundError:
                logger.debug("Table '%s' not found (no data indexed yet)", TABLE_NAME)
                return None
            except Exception as exc:
                msg = str(exc).lower()
                if any(phrase in msg for phrase in _TABLE_NOT_FOUND_PHRASES):
                    logger.debug("Table '%s' not found: %s", TABLE_NAME, exc)
                    return None
                raise

            # Validate table integrity — a corrupted table (e.g. missing data
            # files after a failed indexing run) would fail on any read.
            # count_rows() reads from metadata and succeeds even when data
            # files are missing, so we only probe with head() when rows exist.
            try:
                if self._table.count_rows() > 0:
                    self._table.head(1).to_pydict()
            except Exception as exc:
                logger.warning(
                    "Table '%s' is corrupted and will be dropped: %s",
                    TABLE_NAME,
                    exc,
                )
                try:
                    self.db.drop_table(TABLE_NAME)
                except Exception:
                    logger.warning(
                        "Failed to drop corrupted table '%s'; ignoring",
                        TABLE_NAME,
                    )
                self._table = None
                return None

            # Schema evolution: add PR-1 artifact-graph metadata columns if missing.
            # Existing .guru/ databases created before this PR lack 'kind' and the
            # other three columns.
            schema_names = set(self._table.schema.names)
            if "kind" not in schema_names and self._table.count_rows() > 0:
                logger.info(
                    "Extending existing LanceDB table '%s' with artifact-graph metadata columns",
                    TABLE_NAME,
                )
                try:
                    self._table.add_columns(
                        {
                            "kind": '"text"',
                            "language": '""',
                            "artifact_qualname": '""',
                            "parent_document_id": '""',
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "add_columns failed on table '%s' (%s) — re-materialising from current rows",
                        TABLE_NAME,
                        exc,
                    )
                    # Fallback: drop + recreate with the evolved schema.
                    existing_rows = self._table.to_pandas().to_dict(orient="records")
                    for r in existing_rows:
                        r.setdefault("kind", "text")
                        r.setdefault("language", "")
                        r.setdefault("artifact_qualname", "")
                        r.setdefault("parent_document_id", "")
                    self.db.drop_table(TABLE_NAME)
                    self._table = self.db.create_table(TABLE_NAME, data=existing_rows)
                # Refresh schema names after evolution
                schema_names = set(self._table.schema.names)

            # Schema evolution: add section_breadcrumb column for stable
            # section retrieval after chunk re-splitting.
            if "section_breadcrumb" not in schema_names and self._table.count_rows() > 0:
                logger.info(
                    "Extending existing LanceDB table '%s' with section_breadcrumb column",
                    TABLE_NAME,
                )
                try:
                    self._table.add_columns({"section_breadcrumb": "header_breadcrumb"})
                except Exception as exc:
                    logger.warning(
                        "add_columns(section_breadcrumb) failed on table '%s' (%s) "
                        "— re-materialising from current rows",
                        TABLE_NAME,
                        exc,
                    )
                    existing_rows = self._table.to_pandas().to_dict(orient="records")
                    for r in existing_rows:
                        r.setdefault("section_breadcrumb", r.get("header_breadcrumb", ""))
                    self.db.drop_table(TABLE_NAME)
                    self._table = self.db.create_table(TABLE_NAME, data=existing_rows)
        return self._table

    def add_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks and vectors must have the same length, got {len(chunks)} chunks and {len(vectors)} vectors"
            )
        for i, vector in enumerate(vectors):
            if len(vector) != VECTOR_DIM:
                raise ValueError(
                    f"Vector at index {i} has dimension {len(vector)}, expected {VECTOR_DIM}"
                )
        records = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            records.append(
                {
                    "vector": vector,
                    "content": chunk.content,
                    "file_path": chunk.file_path,
                    "header_breadcrumb": chunk.header_breadcrumb,
                    "section_breadcrumb": chunk.section_breadcrumb or chunk.header_breadcrumb,
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
        table = self._get_table()
        if table is None:
            self._table = self.db.create_table(TABLE_NAME, data=records)
        else:
            table.add(records)

    def chunk_count(self) -> int:
        table = self._get_table()
        if table is None:
            return 0
        return table.count_rows()

    def document_count(self) -> int:
        """Count distinct documents without materializing the full table."""
        table = self._get_table()
        if table is None:
            return 0
        rows = table.search(None).select(["file_path"]).to_list()
        return len({r["file_path"] for r in rows})

    def delete_file(self, file_path: str) -> None:
        """Delete all chunks for a given file path."""
        table = self._get_table()
        if table is None:
            return
        table.delete(f"file_path = '{_escape_sql_string(file_path)}'")

    def delete_files(self, file_paths: list[str]) -> None:
        """Delete all chunks for the given file paths (batch)."""
        table = self._get_table()
        if table is None:
            return
        escaped = ", ".join(f"'{_escape_sql_string(fp)}'" for fp in file_paths)
        table.delete(f"file_path IN ({escaped})")

    def search(
        self, query_vector: list[float], n_results: int = 10, where: str | None = None
    ) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        query = table.search(query_vector).limit(n_results)
        if where:
            query = query.where(where)
        results = query.to_list()
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

    def list_documents(self) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        # Project only needed columns to avoid loading large vector data
        df = table.search(None).select(["file_path", "frontmatter", "labels"]).to_pandas()
        docs = []
        for file_path, group in df.groupby("file_path"):
            first_row = group.iloc[0]
            docs.append(
                {
                    "file_path": file_path,
                    "frontmatter": _parse_json_dict(first_row["frontmatter"]),
                    "labels": _parse_json_list(first_row["labels"]),
                    "chunk_count": len(group),
                }
            )
        return docs

    def get_document(self, file_path: str) -> dict | None:
        table = self._get_table()
        if table is None:
            return None
        rows = (
            table.search(None)
            .where(f"file_path = '{_escape_sql_string(file_path)}'", prefilter=True)
            .select(["content", "file_path", "frontmatter", "labels", "chunk_index"])
            .to_list()
        )
        if not rows:
            return None
        # Sort by chunk_index for stable, ingestion-order reconstruction
        rows.sort(key=lambda r: r.get("chunk_index", 0))
        combined_content = "\n\n".join(r["content"] for r in rows)
        return {
            "file_path": file_path,
            "content": combined_content,
            "frontmatter": _parse_json_dict(rows[0]["frontmatter"]),
            "labels": _parse_json_list(rows[0]["labels"]),
            "chunk_count": len(rows),
        }

    def get_section(self, file_path: str, header_path: str) -> dict | None:
        table = self._get_table()
        if table is None:
            return None
        fp = _escape_sql_string(file_path)
        hp = _escape_sql_string(header_path)
        # Try the stable section_breadcrumb first (handles split chunks).
        # Fall back to exact header_breadcrumb match for databases that
        # pre-date the section_breadcrumb column.
        schema_names = set(table.schema.names)
        if "section_breadcrumb" in schema_names:
            rows = (
                table.search(None)
                .where(
                    f"file_path = '{fp}' AND section_breadcrumb = '{hp}'",
                    prefilter=True,
                )
                .select(
                    [
                        "file_path",
                        "header_breadcrumb",
                        "section_breadcrumb",
                        "content",
                        "chunk_level",
                        "chunk_index",
                    ]
                )
                .to_list()
            )
        else:
            rows = (
                table.search(None)
                .where(
                    f"file_path = '{fp}' AND header_breadcrumb = '{hp}'",
                    prefilter=True,
                )
                .select(["file_path", "header_breadcrumb", "content", "chunk_level"])
                .to_list()
            )
        if not rows:
            return None
        # Sort by chunk_index for stable ordering of split parts
        rows.sort(key=lambda r: r.get("chunk_index", 0))
        combined_content = "\n\n".join(r["content"] for r in rows)
        return {
            "file_path": rows[0]["file_path"],
            "header_breadcrumb": header_path,
            "content": combined_content,
            "chunk_level": int(rows[0]["chunk_level"]),
        }


def _parse_json_list(value: str) -> list:
    """Parse a JSON-encoded list, returning empty list on error."""
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse JSON list: %.100s", value)
        return []


def _parse_json_dict(value: str) -> dict:
    """Parse a JSON-encoded dict, returning empty dict on error."""
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse JSON dict: %.100s", value)
        return {}


def _escape_sql_string(value: str) -> str:
    """Escape single quotes in a SQL string literal."""
    return value.replace("'", "''")
