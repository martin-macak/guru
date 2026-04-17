"""Admin routes — /health, /version. No auth, UDS perm is the trust boundary."""

from __future__ import annotations

from fastapi import APIRouter, Request

from guru_core.graph_types import Health, VersionInfo

from ..versioning import PROTOCOL_VERSION

router = APIRouter()


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    backend = request.app.state.backend
    h = backend.health()
    info = backend.info()
    return Health(
        status="healthy" if h.healthy else "unhealthy",
        graph_reachable=h.healthy,
        backend=info.name,
        backend_version=info.version,
        schema_version=info.schema_version,
    )


@router.get("/version", response_model=VersionInfo)
def version(request: Request) -> VersionInfo:
    info = request.app.state.backend.info()
    return VersionInfo(
        protocol_version=PROTOCOL_VERSION,
        backend=info.name,
        backend_version=info.version,
        schema_version=info.schema_version,
    )
