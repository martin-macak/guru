from __future__ import annotations
import json
import lancedb
from guru_server.ingestion.base import Chunk

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
                return None
            except Exception as exc:
                msg = str(exc).lower()
                if any(phrase in msg for phrase in _TABLE_NOT_FOUND_PHRASES):
                    return None
                raise
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
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            records.append({
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
            })
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
        rows = (
            table.search(None)
            .select(["file_path"])
            .to_list()
        )
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

    def search(self, query_vector: list[float], n_results: int = 10, where: str | None = None) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        query = table.search(query_vector).limit(n_results)
        if where:
            query = query.where(where)
        results = query.to_list()
        return [{"content": r["content"], "file_path": r["file_path"],
                 "header_breadcrumb": r["header_breadcrumb"], "chunk_level": r["chunk_level"],
                 "labels": _parse_json_list(r["labels"]),
                 "score": 1.0 / (1.0 + r.get("_distance", 0.0))} for r in results]

    def list_documents(self) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        # Project only needed columns to avoid loading large vector data
        df = (
            table.search(None)
            .select(["file_path", "frontmatter", "labels"])
            .to_pandas()
        )
        docs = []
        for file_path, group in df.groupby("file_path"):
            first_row = group.iloc[0]
            docs.append({
                "file_path": file_path,
                "frontmatter": _parse_json_dict(first_row["frontmatter"]),
                "labels": _parse_json_list(first_row["labels"]),
                "chunk_count": len(group),
            })
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
        rows = (
            table.search(None)
            .where(
                f"file_path = '{_escape_sql_string(file_path)}'"
                f" AND header_breadcrumb = '{_escape_sql_string(header_path)}'",
                prefilter=True,
            )
            .select(["file_path", "header_breadcrumb", "content", "chunk_level"])
            .to_list()
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "file_path": row["file_path"],
            "header_breadcrumb": row["header_breadcrumb"],
            "content": row["content"],
            "chunk_level": int(row["chunk_level"]),
        }


def _parse_json_list(value: str) -> list:
    """Parse a JSON-encoded list, returning empty list on error."""
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_json_dict(value: str) -> dict:
    """Parse a JSON-encoded dict, returning empty dict on error."""
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _escape_sql_string(value: str) -> str:
    """Escape single quotes in a SQL string literal."""
    return value.replace("'", "''")
