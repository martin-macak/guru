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
        chunks = []
        for i, node in enumerate(nodes):
            header_breadcrumb = self._extract_breadcrumb(node)
            chunk_level = self._infer_level(header_breadcrumb)
            chunk_id = hashlib.sha256(f"{file_path}:{header_breadcrumb}:{i}".encode()).hexdigest()[:16]
            chunks.append(Chunk(
                content=node.get_content(),
                file_path=str(file_path),
                header_breadcrumb=header_breadcrumb,
                chunk_level=chunk_level,
                frontmatter=fm,
                labels=list(rule.labels),
                chunk_id=chunk_id,
            ))
        return chunks

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
