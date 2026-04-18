from __future__ import annotations


class QueryController:
    def __init__(self, session):
        self._session = session

    def is_available(self) -> bool:
        return self._session.can_run_graph_queries()

    async def run_query(self, cypher: str):
        return await self._session.run_query(cypher)
