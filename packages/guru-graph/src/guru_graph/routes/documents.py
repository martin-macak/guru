"""Routes for Document node CRUD operations.

Document nodes are distinct from Artifact nodes — they represent the
sync-layer's view of indexed documents under a KB, not the ingestion-
pipeline graph artefacts. Both can coexist under a :Kb node.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

router = APIRouter()


class DocumentUpsert(BaseModel):
    id: str
    title: str
    path: str
    metadata: dict = Field(default_factory=dict)


@router.get("/graph/documents/{kb}")
def list_document_nodes(kb: str, request: Request):
    backend = request.app.state.backend
    rows = backend.list_document_nodes(kb)
    return {"nodes": rows}


@router.post("/graph/documents/{kb}", status_code=status.HTTP_204_NO_CONTENT)
def upsert_document_node(kb: str, body: DocumentUpsert, request: Request):
    backend = request.app.state.backend
    backend.upsert_document_node(kb=kb, document=body.model_dump())


@router.delete("/graph/documents/{kb}/{doc_id:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_node(kb: str, doc_id: str, request: Request):
    backend = request.app.state.backend
    backend.delete_document_node(kb=kb, doc_id=doc_id)
