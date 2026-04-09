from __future__ import annotations
import hashlib
import re
from pathlib import Path
import frontmatter
from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser as LlamaMarkdownParser
from guru_core.types import Rule
from guru_server.ingestion.base import Chunk, DocumentParser

_HEADING_RE = re.compile(r"^#+\s+(.+)", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"```", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|", re.MULTILINE)


def _detect_content_type(content: str) -> str:
    has_code = bool(_CODE_BLOCK_RE.search(content))
    has_table = bool(_TABLE_ROW_RE.search(content))
    if has_code and has_table:
        return "mixed"
    if has_code:
        return "code"
    if has_table:
        return "table"
    return "text"


class MarkdownParser(DocumentParser):
    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in (".md", ".markdown")

    def parse(self, file_path: Path, rule: Rule) -> list[Chunk]:
        raw = file_path.read_text(encoding="utf-8")
        post = frontmatter.loads(raw)
        fm = dict(post.metadata)
        doc = Document(text=post.content, metadata={"source": str(file_path)})
        parser = LlamaMarkdownParser()
        nodes = parser.get_nodes_from_documents([doc])

        # Determine chunking config
        split_level = None
        max_tokens = None
        if rule.chunking is not None:
            split_level = rule.chunking.split_level  # e.g. "h2" or "h3"
            max_tokens = rule.chunking.max_tokens

        chunks: list[Chunk] = []
        for i, node in enumerate(nodes):
            header_breadcrumb = self._extract_breadcrumb(node)
            chunk_level = self._infer_level(header_breadcrumb)
            chunk_id = hashlib.sha256(f"{file_path}:{header_breadcrumb}:{i}".encode()).hexdigest()[:16]
            content = node.get_content()
            metadata: dict = {}
            if max_tokens is not None:
                metadata["max_tokens"] = max_tokens
            chunks.append(Chunk(
                content=content,
                file_path=str(file_path),
                header_breadcrumb=header_breadcrumb,
                chunk_level=chunk_level,
                frontmatter=fm,
                labels=list(rule.labels),
                chunk_id=chunk_id,
                content_type=_detect_content_type(content),
            ))

        # Apply split_level: if "h2", merge level-3 chunks into their parent level-2 chunk
        if split_level == "h2":
            chunks = self._merge_h3_into_h2(chunks)

        # Wire up parent_chunk_id: level-3 chunks point to their enclosing level-2 chunk
        self._assign_parent_ids(chunks)

        return chunks

    def _merge_h3_into_h2(self, chunks: list[Chunk]) -> list[Chunk]:
        """Merge level-3 chunks into the preceding level-2 chunk."""
        merged: list[Chunk] = []
        current_parent: Chunk | None = None
        for chunk in chunks:
            if chunk.chunk_level <= 2:
                current_parent = chunk
                merged.append(chunk)
            else:
                # chunk_level == 3: append content to parent
                if current_parent is not None:
                    current_parent.content = current_parent.content + "\n\n" + chunk.content
                    current_parent.content_type = _detect_content_type(current_parent.content)
                else:
                    # No parent found yet; keep chunk as-is
                    merged.append(chunk)
        return merged

    def _assign_parent_ids(self, chunks: list[Chunk]) -> None:
        """Level-3 chunks point to the level-2 chunk they're under."""
        current_l2: Chunk | None = None
        for chunk in chunks:
            if chunk.chunk_level == 2:
                current_l2 = chunk
            elif chunk.chunk_level == 3 and current_l2 is not None:
                chunk.parent_chunk_id = current_l2.chunk_id

    def _extract_breadcrumb(self, node) -> str:
        metadata = node.metadata or {}
        # LlamaIndex MarkdownNodeParser uses 'header_path' like '/Authentication/Token Refresh/'
        # This represents the *parent* path; the node's own heading is in the content.
        header_path = metadata.get("header_path", "")
        parent_parts: list[str] = []
        if header_path and header_path != "/":
            parent_parts = [p for p in header_path.strip("/").split("/") if p]

        # Extract the node's own first heading from the content
        content = node.get_content() or ""
        own_heading: str | None = None
        match = _HEADING_RE.search(content)
        if match:
            own_heading = match.group(1).strip()

        # Build breadcrumb: parent path parts + own heading (if not already the last parent part)
        if own_heading and (not parent_parts or parent_parts[-1] != own_heading):
            parts = parent_parts + [own_heading]
        elif parent_parts:
            parts = parent_parts
        else:
            parts = []

        return " > ".join(parts) if parts else "Document"

    def _infer_level(self, breadcrumb: str) -> int:
        if breadcrumb == "Document":
            return 1
        return min(breadcrumb.count(" > ") + 1, 3)
