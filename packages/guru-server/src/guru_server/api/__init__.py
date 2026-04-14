from fastapi import APIRouter

from guru_server.api.cache import router as cache_router
from guru_server.api.documents import router as documents_router
from guru_server.api.index import router as index_router
from guru_server.api.jobs import router as jobs_router
from guru_server.api.search import router as search_router
from guru_server.api.status import router as status_router

api_router = APIRouter()
api_router.include_router(search_router)
api_router.include_router(documents_router)
api_router.include_router(index_router)
api_router.include_router(jobs_router)
api_router.include_router(status_router)
api_router.include_router(cache_router)
