from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from guru_server.api.models import GraphBootOut, ProjectBootOut, WebBootOut, WebRuntimeOut
from guru_server.web_runtime import open_web_browser

router = APIRouter()


class WebOpenOut(BaseModel):
    opened: bool
    url: str | None = None


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


@router.post("/web/open", response_model=WebOpenOut)
def web_open(request: Request) -> WebOpenOut:
    runtime = request.app.state.web_runtime
    return WebOpenOut(opened=open_web_browser(runtime.url), url=runtime.url)
