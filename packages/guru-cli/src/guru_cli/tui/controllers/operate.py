from __future__ import annotations


class OperateController:
    def __init__(self, session) -> None:
        self._session = session

    async def refresh(self):
        return await self._session.load_status()

    async def reindex(self) -> str:
        return await self._session.trigger_reindex()
