import fnmatch
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class IndexBody(BaseModel):
    path: str | None = None


@router.post("/index")
async def trigger_index(body: IndexBody, request: Request):
    store = request.app.state.store
    embedder = request.app.state.embedder
    config = request.app.state.config
    project_root = request.app.state.project_root

    target = Path(body.path) if body.path else Path(project_root)

    from guru_server.ingestion.markdown import MarkdownParser
    parser = MarkdownParser()

    all_chunks = []
    for rule in config:
        if rule.exclude:
            continue
        for file_path in target.rglob("*"):
            if not file_path.is_file():
                continue
            if not fnmatch.fnmatch(str(file_path.relative_to(target)), rule.match.glob):
                continue
            # Check if any exclude rule matches
            excluded = False
            for exc_rule in config:
                if exc_rule.exclude and fnmatch.fnmatch(
                    str(file_path.relative_to(target)), exc_rule.match.glob
                ):
                    excluded = True
                    break
            if excluded:
                continue
            if parser.supports(file_path):
                chunks = parser.parse(file_path, rule)
                all_chunks.extend(chunks)

    if all_chunks:
        texts = [chunk.content for chunk in all_chunks]
        vectors = await embedder.embed_batch(texts)
        store.add_chunks(all_chunks, vectors)

    return {
        "indexed": len(all_chunks),
        "documents": len({c.file_path for c in all_chunks}),
    }
