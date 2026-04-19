from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, constr

from guru_core.graph_types import DocumentSearchHit
from guru_server.api.models import DocumentListItem, DocumentOut, SectionOut

router = APIRouter()


class DocumentSearchBody(BaseModel):
    query: constr(min_length=1, max_length=500)  # type: ignore[valid-type]
    limit: int = Field(20, ge=1, le=100)


class DocumentSearchResponse(BaseModel):
    hits: list[DocumentSearchHit]


_ALLOWED_DOCUMENT_FILTERS = {"labels"}


@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents(request: Request):
    query_keys = set(request.query_params.keys())
    unsupported = sorted(query_keys - _ALLOWED_DOCUMENT_FILTERS)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported document filters: {', '.join(unsupported)}. Allowed: {sorted(_ALLOWED_DOCUMENT_FILTERS)}",
        )

    store = request.app.state.store
    documents = store.list_documents()

    label_values = request.query_params.getlist("labels")
    if label_values:
        # Support comma-separated values per param (e.g., ?labels=spec,security)
        requested_labels: set[str] = set()
        for value in label_values:
            for part in value.split(","):
                part = part.strip()
                if part:
                    requested_labels.add(part)
        documents = [
            doc for doc in documents if requested_labels.issubset(set(doc.get("labels", [])))
        ]

    return documents


@router.get("/documents/{path:path}/sections/{header_path:path}", response_model=SectionOut)
async def get_section(path: str, header_path: str, request: Request):
    store = request.app.state.store
    section = store.get_section(path, header_path)
    if section is None:
        raise HTTPException(status_code=404, detail=f"Section not found: {header_path}")
    return section


@router.get("/documents/{path:path}", response_model=DocumentOut)
async def get_document(path: str, request: Request):
    store = request.app.state.store
    doc = store.get_document(path)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")
    return doc


@router.post("/documents/search", response_model=DocumentSearchResponse)
async def documents_search(body: DocumentSearchBody, request: Request) -> DocumentSearchResponse:
    store = request.app.state.store
    embedder = request.app.state.embedder

    query_vector = await embedder.embed(body.query)
    rows = store.search(query_vector=query_vector, n_results=body.limit)

    hits: list[DocumentSearchHit] = []
    seen_paths: set[str] = set()
    for row in rows:
        path = row.get("file_path") or row.get("path", "")
        if path in seen_paths:
            continue
        seen_paths.add(path)
        hits.append(
            DocumentSearchHit(
                path=path,
                title=row.get("title") or row.get("header_breadcrumb") or path,
                excerpt=row.get("excerpt") or row.get("content", "")[:200],
                score=float(row["score"]),
            )
        )
    return DocumentSearchResponse(hits=hits)
