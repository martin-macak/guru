from fastapi import APIRouter, Request

from guru_server.api.models import StatusOut

router = APIRouter()


@router.get("/status", response_model=StatusOut)
async def get_status(request: Request):
    store = request.app.state.store
    return {
        "server_running": True,
        "document_count": len(store.list_documents()),
        "chunk_count": store.chunk_count(),
        "last_indexed": request.app.state.last_indexed,
        "ollama_available": True,
        "model_loaded": True,
    }
