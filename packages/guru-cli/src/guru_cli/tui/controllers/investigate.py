from __future__ import annotations

from guru_cli.tui.state import WorkbenchState


class InvestigateController:
    def __init__(self, session) -> None:
        self._session = session

    async def search(
        self,
        state: WorkbenchState,
        query: str,
    ) -> tuple[WorkbenchState, list]:
        hits = await self._session.run_search(query)
        return state, hits
