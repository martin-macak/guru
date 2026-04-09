from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/documents")
async def list_documents(request: Request):
    store = request.app.state.store
    return store.list_documents()


@router.get("/documents/{path:path}/sections/{header_path:path}")
async def get_section(path: str, header_path: str, request: Request):
    store = request.app.state.store
    section = store.get_section(path, header_path)
    if section is None:
        raise HTTPException(status_code=404, detail=f"Section not found: {header_path}")
    return section


@router.get("/documents/{path:path}")
async def get_document(path: str, request: Request):
    store = request.app.state.store
    doc = store.get_document(path)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")
    return doc
