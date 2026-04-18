from __future__ import annotations

from fastapi import APIRouter, Request

from guru_server.api.models import GraphBootOut, ProjectBootOut, WebBootOut, WebRuntimeOut

router = APIRouter()


@router.get("/web/boot", response_model=WebBootOut)
def web_boot(request: Request) -> WebBootOut:
    runtime = request.app.state.web_runtime
    return WebBootOut(
        project=ProjectBootOut(
            name=request.app.state.project_name,
            root=str(request.app.state.project_root),
        ),
        web=WebRuntimeOut(
            enabled=runtime.enabled,
            available=runtime.available,
            url=runtime.url,
            reason=runtime.reason,
            auto_open=runtime.auto_open,
        ),
        graph=GraphBootOut(enabled=bool(request.app.state.graph_enabled)),
    )
