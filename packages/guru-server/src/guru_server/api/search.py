from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter()


class SearchBody(BaseModel):
    query: str
    n_results: int = 10
    filters: dict[str, str] = Field(default_factory=dict)


@router.post("/search")
async def search(body: SearchBody, request: Request):
    store = request.app.state.store
    embedder = request.app.state.embedder

    query_vector = await embedder.embed(body.query)

    where = None
    if body.filters:
        conditions = []
        for key, value in body.filters.items():
            conditions.append(f"{key} LIKE '%{value}%'")
        where = " AND ".join(conditions)

    return store.search(
        query_vector=query_vector,
        n_results=body.n_results,
        where=where,
    )
