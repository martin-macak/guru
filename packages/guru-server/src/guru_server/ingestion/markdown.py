from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path

import frontmatter
from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser as LlamaMarkdownParser

from guru_core.types import Rule
from guru_server.ingestion.base import Chunk, DocumentParser, GraphEdge, GraphNode, ParseResult

_HEADING_RE = re.compile(r"^#+\s+(.+)", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"```", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|", re.MULTILINE)

# nomic-embed-text has a 2048-token context window.
# Leave headroom for special tokens the model prepends.
DEFAULT_TOKEN_BUDGET = 1900

# Sentence-ending punctuation followed by a space (or end of string).
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


def _split_on_paragraphs(text: str) -> list[str]:
    """Split text on blank lines (paragraph boundaries)."""
    parts = re.split(r"\n\n+", text)
    return [p for p in parts if p.strip()]


def _split_on_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries."""
    parts = _SENTENCE_RE.split(text)
    return [p for p in parts if p.strip()]


def _merge_segments(segments: list[str], budget: int, separator: str) -> list[str]:
    """Greedily merge small segments until the budget would be exceeded."""
    merged: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for seg in segments:
        seg_tokens = _estimate_tokens(seg)
        # If adding this segment would exceed budget, flush current
        if current and current_tokens + _estimate_tokens(separator) + seg_tokens > budget:
            merged.append(separator.join(current))
            current = [seg]
            current_tokens = seg_tokens
        else:
            current.append(seg)
            current_tokens += (0 if not current[:-1] else _estimate_tokens(separator)) + seg_tokens
    if current:
        merged.append(separator.join(current))
    return merged


def _hard_split(text: str, budget: int) -> list[str]:
    """Split text into pieces of at most ``budget * 4`` characters."""
    max_chars = budget * 4
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _resplit_chunk(chunk: Chunk, budget: int = DEFAULT_TOKEN_BUDGET) -> list[Chunk]:
    """Re-split a chunk that exceeds *budget* tokens.

    Split priority:
    1. Paragraph breaks (blank lines)
    2. Sentence boundaries
    3. Hard character cut as last resort

    Returns a list of chunks. If the original chunk is within budget,
    it is returned as-is in a single-element list.
    """
    if _estimate_tokens(chunk.content) <= budget:
        return [chunk]

    # --- Stage 1: split on paragraphs, then merge small paragraphs back ---
    paragraphs = _split_on_paragraphs(chunk.content)
    pieces = _merge_segments(paragraphs, budget, "\n\n")

    # --- Stage 2: any piece still over budget → split on sentences ---
    refined: list[str] = []
    for piece in pieces:
        if _estimate_tokens(piece) <= budget:
            refined.append(piece)
        else:
            sentences = _split_on_sentences(piece)
            refined.extend(_merge_segments(sentences, budget, " "))

    # --- Stage 3: hard cut anything still over budget ---
    final: list[str] = []
    for piece in refined:
        if _estimate_tokens(piece) <= budget:
            final.append(piece)
        else:
            final.extend(_hard_split(piece, budget))

    # Build sub-chunks preserving all metadata
    sub_chunks: list[Chunk] = []
    for i, text in enumerate(final):
        part_label = f"#part-{i + 1}"
        sub_id = hashlib.sha256(
            f"{chunk.chunk_id}:{part_label}".encode()
        ).hexdigest()[:16]
        sub_chunks.append(
            replace(
                chunk,
                content=text,
                header_breadcrumb=f"{chunk.header_breadcrumb}{part_label}",
                chunk_id=sub_id,
                content_type=_detect_content_type(text),
            )
        )
    return sub_chunks


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


def _sanitize_frontmatter(obj):
    """Recursively convert non-JSON-serializable values to strings.

    YAML parsing produces datetime.date/datetime objects that json.dumps
    cannot handle. Convert them to ISO-format strings.
    """
    import datetime

    if isinstance(obj, dict):
        return {k: _sanitize_frontmatter(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_frontmatter(v) for v in obj]
    if isinstance(obj, datetime.datetime | datetime.date):
        return obj.isoformat()
    return obj


class MarkdownParser(DocumentParser):
    @property
    def name(self) -> str:
        return "markdown"

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in (".md", ".markdown")

    def parse(self, file_path: Path, rule: Rule, *, kb_name: str, rel_path: str) -> ParseResult:
        raw = file_path.read_text(encoding="utf-8")
        post = frontmatter.loads(raw)
        fm = _sanitize_frontmatter(dict(post.metadata))
        doc = Document(text=post.content, metadata={"source": str(file_path)})
        parser = LlamaMarkdownParser()
        nodes = parser.get_nodes_from_documents([doc])

        split_level = None
        if rule.chunking is not None:
            split_level = rule.chunking.split_level

        document_id = f"{kb_name}::{rel_path}"
        document_node = GraphNode(
            node_id=document_id,
            label="Document",
            properties={
                "kb_name": kb_name,
                "relative_path": rel_path,
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
            chunk_id = hashlib.sha256(f"{file_path}:{header_breadcrumb}:{i}".encode()).hexdigest()[
                :16
            ]
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
            # After merging, level-3 chunks were absorbed into their level-2 parents.
            # Filter section_nodes to match surviving chunks so the graph and vector
            # index stay aligned — a section node must have a corresponding chunk.
            surviving_breadcrumbs = {c.header_breadcrumb for c in chunks}
            section_nodes = [
                sn for sn in section_nodes if sn.properties["breadcrumb"] in surviving_breadcrumbs
            ]

        # Re-split any chunk that exceeds the embedder's token budget.
        chunks = self._resplit_oversized(chunks)

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

    @staticmethod
    def _resplit_oversized(
        chunks: list[Chunk], budget: int = DEFAULT_TOKEN_BUDGET
    ) -> list[Chunk]:
        """Re-split any chunk exceeding the token *budget*."""
        result: list[Chunk] = []
        for chunk in chunks:
            result.extend(_resplit_chunk(chunk, budget))
        return result

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
            parts = [*parent_parts, own_heading]
        elif parent_parts:
            parts = parent_parts
        else:
            parts = []

        return " > ".join(parts) if parts else "Document"

    def _infer_level(self, breadcrumb: str) -> int:
        if breadcrumb == "Document":
            return 1
        return min(breadcrumb.count(" > ") + 1, 3)
