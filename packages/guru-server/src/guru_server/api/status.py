from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/status")
async def get_status(request: Request):
    store = request.app.state.store
    return {
        "server_running": True,
        "document_count": len(store.list_documents()),
        "chunk_count": store.chunk_count(),
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
    }
