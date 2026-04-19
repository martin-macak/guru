from __future__ import annotations

from unittest.mock import MagicMock

from guru_server.startup import run_startup_reconcile


def test_startup_reconcile_runs_when_graph_enabled():
    sync = MagicMock()
    sync.status.return_value = MagicMock(graph_enabled=True, drift=2)
    run_startup_reconcile(sync)
    sync.reconcile.assert_called_once()


def test_startup_reconcile_skips_when_graph_disabled():
    sync = MagicMock()
    sync.status.return_value = MagicMock(graph_enabled=False, drift=5)
    run_startup_reconcile(sync)
    sync.reconcile.assert_not_called()


def test_startup_reconcile_skips_when_no_drift():
    sync = MagicMock()
    sync.status.return_value = MagicMock(graph_enabled=True, drift=0)
    run_startup_reconcile(sync)
    sync.reconcile.assert_not_called()
