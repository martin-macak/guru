from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from guru_core.graph_types import SyncStatus

router = APIRouter(prefix="/sync")


@router.get("/status", response_model=SyncStatus)
def sync_status(request: Request) -> SyncStatus:
    return request.app.state.sync.status()


@router.post("/reconcile", response_model=SyncStatus)
def sync_reconcile(request: Request) -> SyncStatus:
    sync = request.app.state.sync
    if not sync.graph_enabled():
        raise HTTPException(status_code=409, detail="graph is disabled")
    return sync.reconcile()
