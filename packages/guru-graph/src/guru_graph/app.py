"""FastAPI app factory for the guru-graph daemon."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .backend.base import GraphBackend
from .routes import admin, kbs, query
from .versioning import (
    PROTOCOL_HEADER,
    PROTOCOL_VERSION,
    VersionNegotiationError,
    negotiate_protocol,
    parse_version,
)

logger = logging.getLogger(__name__)


def create_app(*, backend: GraphBackend) -> FastAPI:
    app = FastAPI(title="guru-graph", version=PROTOCOL_VERSION)
    app.state.backend = backend

    @app.middleware("http")
    async def protocol_version_middleware(request: Request, call_next):
        header = request.headers.get(PROTOCOL_HEADER)
        if header:
            try:
                client = parse_version(header)
                negotiate_protocol(
                    server=parse_version(PROTOCOL_VERSION),
                    client=client,
                )
            except VersionNegotiationError as e:
                return JSONResponse(
                    status_code=426,
                    content={
                        "error": "protocol_upgrade_required",
                        "detail": str(e),
                        "supported": [f"{parse_version(PROTOCOL_VERSION).major}.x"],
                    },
                )
        response = await call_next(request)
        response.headers[PROTOCOL_HEADER] = PROTOCOL_VERSION
        return response

    app.include_router(admin.router)
    app.include_router(kbs.router)
    app.include_router(query.router)
    return app
