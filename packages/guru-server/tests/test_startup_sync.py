from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from guru_server.startup import run_startup_reconcile


@pytest.mark.asyncio
async def test_startup_reconcile_runs_when_graph_enabled():
    sync = MagicMock()
    sync.status = AsyncMock(return_value=MagicMock(graph_enabled=True, drift=2))
    sync.reconcile = AsyncMock()
    await run_startup_reconcile(sync)
    sync.reconcile.assert_awaited_once()


@pytest.mark.asyncio
async def test_startup_reconcile_skips_when_graph_disabled():
    sync = MagicMock()
    sync.status = AsyncMock(return_value=MagicMock(graph_enabled=False, drift=5))
    sync.reconcile = AsyncMock()
    await run_startup_reconcile(sync)
    sync.reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_reconcile_skips_when_no_drift():
    sync = MagicMock()
    sync.status = AsyncMock(return_value=MagicMock(graph_enabled=True, drift=0))
    sync.reconcile = AsyncMock()
    await run_startup_reconcile(sync)
    sync.reconcile.assert_not_awaited()
