import fnmatch
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from guru_server.api.models import IndexOut

router = APIRouter()


class IndexBody(BaseModel):
    path: str | None = None


@router.post("/index", response_model=IndexOut)
async def trigger_index(body: IndexBody, request: Request):
    store = request.app.state.store
    embedder = request.app.state.embedder
    config = request.app.state.config
    project_root = request.app.state.project_root

    target = Path(body.path) if body.path else Path(project_root)

    from guru_server.ingestion.markdown import MarkdownParser
    parser = MarkdownParser()

    # Build exclude patterns
    exclude_patterns = [r.match.glob for r in config if r.exclude]

    # Collect files by globbing each include rule directly
    all_chunks = []
    seen_files: set[str] = set()

    for rule in config:
        if rule.exclude:
            continue
        for file_path in target.glob(rule.match.glob):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(target))
            if rel in seen_files:
                continue
            # Check exclude rules
            if any(fnmatch.fnmatch(rel, ep) for ep in exclude_patterns):
                continue
            if parser.supports(file_path):
                seen_files.add(rel)
                chunks = parser.parse(file_path, rule)
                all_chunks.extend(chunks)

    if all_chunks:
        texts = [chunk.content for chunk in all_chunks]
        vectors = await embedder.embed_batch(texts)
        store.add_chunks(all_chunks, vectors)

    request.app.state.last_indexed = datetime.now(timezone.utc)

    return {
        "indexed": len(all_chunks),
        "documents": len({c.file_path for c in all_chunks}),
    }
