from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from guru_core.types import (
    CacheDeleteResult,
    CachePruneRequest,
    CacheStatsOut,
    DocumentListItem,
    DocumentOut,
    IndexAccepted,
    IndexOut,
    JobDetail,
    JobSummary,
    SearchResultOut,
    SectionOut,
)
from guru_core.types import (
    StatusOut as CoreStatusOut,
)


class WebRuntimeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = False
    available: bool = False
    url: str | None = None
    reason: str | None = None
    auto_open: bool = Field(default=False, alias="autoOpen")


class ProjectBootOut(BaseModel):
    name: str
    root: str


class GraphBootOut(BaseModel):
    enabled: bool


class WebBootOut(BaseModel):
    project: ProjectBootOut
    web: WebRuntimeOut
    graph: GraphBootOut


class StatusOut(CoreStatusOut):
    web: WebRuntimeOut = Field(default_factory=WebRuntimeOut)


__all__ = [
    "CacheDeleteResult",
    "CachePruneRequest",
    "CacheStatsOut",
    "DocumentListItem",
    "DocumentOut",
    "GraphBootOut",
    "IndexAccepted",
    "IndexOut",
    "JobDetail",
    "JobSummary",
    "ProjectBootOut",
    "SearchResultOut",
    "SectionOut",
    "StatusOut",
    "WebBootOut",
    "WebRuntimeOut",
]
