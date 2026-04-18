from __future__ import annotations


class GraphController:
    def __init__(self, session) -> None:
        self._session = session

    async def load_neighborhood(self, node_id: str, depth: int = 1):
        return await self._session.load_graph_neighbors(node_id, depth=depth)
