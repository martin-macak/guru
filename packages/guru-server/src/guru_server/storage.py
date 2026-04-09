from __future__ import annotations
import json
import lancedb
from guru_server.ingestion.base import Chunk

VECTOR_DIM = 768
TABLE_NAME = "chunks"

class VectorStore:
    def __init__(self, db_path: str):
        self.db = lancedb.connect(db_path)
        self._table = None

    def _get_table(self):
        if self._table is None:
            try:
                self._table = self.db.open_table(TABLE_NAME)
            except Exception:
                return None
        return self._table

    def add_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        records = []
        for chunk, vector in zip(chunks, vectors):
            records.append({
                "vector": vector,
                "content": chunk.content,
                "file_path": chunk.file_path,
                "header_breadcrumb": chunk.header_breadcrumb,
                "chunk_level": chunk.chunk_level,
                "frontmatter": json.dumps(chunk.frontmatter),
                "labels": json.dumps(chunk.labels),
                "chunk_id": chunk.chunk_id or "",
                "parent_chunk_id": chunk.parent_chunk_id or "",
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
                 "labels": r["labels"], "score": 1.0 - r.get("_distance", 0.0)} for r in results]

    def list_documents(self) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        df = table.to_pandas()
        docs = []
        for file_path, group in df.groupby("file_path"):
            first_row = group.iloc[0]
            docs.append({"file_path": file_path, "frontmatter": first_row["frontmatter"],
                         "labels": first_row["labels"], "chunk_count": len(group)})
        return docs

    def get_document(self, file_path: str) -> dict | None:
        table = self._get_table()
        if table is None:
            return None
        df = table.to_pandas()
        doc_chunks = df[df["file_path"] == file_path]
        if doc_chunks.empty:
            return None
        first_row = doc_chunks.iloc[0]
        combined_content = "\n\n".join(doc_chunks["content"].tolist())
        return {"file_path": file_path, "content": combined_content,
                "frontmatter": first_row["frontmatter"], "labels": first_row["labels"],
                "chunk_count": len(doc_chunks)}

    def get_section(self, file_path: str, header_path: str) -> dict | None:
        table = self._get_table()
        if table is None:
            return None
        df = table.to_pandas()
        matches = df[(df["file_path"] == file_path) & (df["header_breadcrumb"] == header_path)]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return {"file_path": row["file_path"], "header_breadcrumb": row["header_breadcrumb"],
                "content": row["content"], "chunk_level": int(row["chunk_level"])}
