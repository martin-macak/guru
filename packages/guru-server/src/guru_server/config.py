from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from guru_core.config import DEFAULT_RULES, federation_dir, merge_rules
from guru_core.types import (
    GraphConfig,
    MatchConfig,
    Rule,
)
from guru_core.types import (
    GuruConfig as CoreGuruConfig,
)


class WebConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = True
    auto_open: bool = Field(default=False, alias="autoOpen")


class GuruConfig(CoreGuruConfig):
    web: WebConfig = Field(default_factory=WebConfig)


def load_config(path: Path) -> GuruConfig | None:
    """Load a Guru config file, including server-local web settings."""
    if not path.is_file():
        return None
    with path.open() as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"version": 1, "rules": data}
    return GuruConfig.model_validate(data)


def load_rules(path: Path) -> list[Rule] | None:
    """Backward-compatible alias returning only the rule list."""
    cfg = load_config(path)
    if cfg is None:
        return None
    return cfg.rules


def resolve_web_config(config: CoreGuruConfig | GuruConfig | None) -> WebConfig:
    if config is None:
        return WebConfig()
    web = getattr(config, "web", None)
    if isinstance(web, WebConfig):
        return web
    if web is None:
        return WebConfig()
    return WebConfig.model_validate(web)


def resolve_config(
    project_root: Path,
    global_config_dir: Path | None = None,
) -> GuruConfig:
    """Resolve configuration using the fallback chain."""
    if global_config_dir is None:
        global_config_dir = Path.home() / ".config" / "guru"

    global_cfg = load_config(global_config_dir / "config.json")

    local_cfg = load_config(project_root / ".guru.json")
    if local_cfg is None:
        local_cfg = load_config(project_root / "guru.json")
    if local_cfg is None:
        local_cfg = load_config(project_root / ".guru" / "config.json")

    if global_cfg is None and local_cfg is None:
        return GuruConfig(version=1, rules=list(DEFAULT_RULES))

    if global_cfg is None:
        return local_cfg

    if local_cfg is None:
        return global_cfg

    merged_rules = merge_rules(global_cfg.rules, local_cfg.rules)
    return GuruConfig(
        version=1,
        rules=merged_rules,
        name=local_cfg.name if local_cfg.name is not None else global_cfg.name,
        graph=local_cfg.graph if local_cfg.graph is not None else global_cfg.graph,
        web=resolve_web_config(local_cfg),
    )


__all__ = [
    "DEFAULT_RULES",
    "GraphConfig",
    "GuruConfig",
    "MatchConfig",
    "Rule",
    "WebConfig",
    "federation_dir",
    "load_config",
    "load_rules",
    "merge_rules",
    "resolve_config",
    "resolve_web_config",
]
