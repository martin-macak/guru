from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from guru_server.api.models import IndexOut

router = APIRouter()

# Patterns containing '**' require Path.glob(); fnmatch does not support recursive '**'.
# We keep exclude patterns as-is and apply them via glob subtraction (see below).


class IndexBody(BaseModel):
    path: str | None = None


@router.post("/index", response_model=IndexOut)
async def trigger_index(body: IndexBody, request: Request):
    store = request.app.state.store
    embedder = request.app.state.embedder
    config = request.app.state.config
    project_root = Path(request.app.state.project_root).resolve()

    if body.path:
        target = (project_root / body.path).resolve()
        # Prevent path traversal: target must be inside project_root
        if not target.is_relative_to(project_root):
            raise HTTPException(status_code=400, detail="path must be within the project root")
    else:
        target = project_root

    from guru_server.ingestion.markdown import MarkdownParser

    parser = MarkdownParser()

    # Collect the set of files excluded by any exclude rule (using Path.glob for ** support)
    excluded_files: set[Path] = set()
    for rule in config:
        if rule.exclude:
            excluded_files.update(target.glob(rule.match.glob))

    # Collect files by globbing each include rule
    all_chunks = []
    seen_files: set[Path] = set()

    for rule in config:
        if rule.exclude:
            continue
        for file_path in target.glob(rule.match.glob):
            if not file_path.is_file():
                continue
            if file_path in excluded_files:
                continue
            if file_path in seen_files:
                continue
            if parser.supports(file_path):
                seen_files.add(file_path)
                chunks = parser.parse(file_path, rule)
                # Store paths relative to project_root for portability
                rel_path = str(file_path.relative_to(project_root))
                for chunk in chunks:
                    chunk.file_path = rel_path
                all_chunks.extend(chunks)

    if all_chunks:
        # Remove existing chunks for these files before re-indexing to prevent duplicates
        indexed_paths = list({c.file_path for c in all_chunks})
        store.delete_files(indexed_paths)

        texts = [chunk.content for chunk in all_chunks]
        vectors = await embedder.embed_batch(texts)
        store.add_chunks(all_chunks, vectors)

    request.app.state.last_indexed = datetime.now(UTC)

    return {
        "indexed": len(all_chunks),
        "documents": len({c.file_path for c in all_chunks}),
    }
