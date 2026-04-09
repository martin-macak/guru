from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from guru_server.api.models import SearchResultOut
from guru_server.storage import _escape_sql_string

router = APIRouter()

# Only allow filtering on these known columns to prevent injection
_ALLOWED_FILTER_COLUMNS = {"labels"}


class SearchBody(BaseModel):
    query: str
    n_results: int = 10
    filters: dict[str, str] = Field(default_factory=dict)


@router.post("/search", response_model=list[SearchResultOut])
async def search(body: SearchBody, request: Request):
    store = request.app.state.store
    embedder = request.app.state.embedder

    query_vector = await embedder.embed(body.query)

    where = None
    if body.filters:
        unknown = set(body.filters) - _ALLOWED_FILTER_COLUMNS
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported filter columns: {sorted(unknown)}. Allowed: {sorted(_ALLOWED_FILTER_COLUMNS)}",
            )
        conditions = []
        for key, value in body.filters.items():
            conditions.append(f"{key} LIKE '%{_escape_sql_string(value)}%'")
        where = " AND ".join(conditions)

    return store.search(
        query_vector=query_vector,
        n_results=body.n_results,
        where=where,
    )
