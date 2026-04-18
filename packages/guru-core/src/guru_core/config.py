from __future__ import annotations

import json
from pathlib import Path

from guru_core.types import GuruConfig, MatchConfig, Rule

DEFAULT_RULES = [
    Rule(rule_name="default", match=MatchConfig(glob="**/*.md")),
]


def load_config(path: Path) -> GuruConfig | None:
    """Load a config file. Returns None if the file does not exist.

    Accepts both the v1 object format (`{"version": 1, "rules": [...]}`)
    and the legacy flat-array format (`[{"ruleName": ..., ...}]`), which
    is auto-wrapped into `{"version": 1, "rules": <array>}` for callers.
    """
    if not path.is_file():
        return None
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"version": 1, "rules": data}
    return GuruConfig(**data)


# Keep load_rules as backward-compat alias
def load_rules(path: Path) -> list[Rule] | None:
    """Load rules from a JSON config file. Returns None if file doesn't exist.

    .. deprecated:: Use load_config() instead.
    """
    cfg = load_config(path)
    if cfg is None:
        return None
    return cfg.rules


def merge_rules(global_rules: list[Rule], local_rules: list[Rule]) -> list[Rule]:
    """Merge local rules over global rules.

    Rules with the same rule_name in local fully replace the global version.
    Local rules with new names are appended.
    """
    merged = {r.rule_name: r for r in global_rules}
    for rule in local_rules:
        merged[rule.rule_name] = rule
    return list(merged.values())


def resolve_config(
    project_root: Path,
    global_config_dir: Path | None = None,
) -> GuruConfig:
    """Resolve configuration using the fallback chain.

    Resolution:
    1. Load ~/.config/guru/config.json as base (global)
    2. Load ./.guru.json (preferred), ./guru.json (backwards compat),
       or ./.guru/config.json (legacy fallback) as local
    3. Merge rules: local rules override global by rule_name, new names appended
    4. No config anywhere -> GuruConfig with DEFAULT_RULES
    """
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
    # Local fields win over global; global provides defaults for any field
    # the local config didn't set. Applies to `name` and `graph` today, and
    # to any future top-level field without touching this call site.
    return GuruConfig(
        version=1,
        rules=merged_rules,
        name=local_cfg.name if local_cfg.name is not None else global_cfg.name,
        graph=local_cfg.graph if local_cfg.graph is not None else global_cfg.graph,
    )


def federation_dir() -> Path:
    """Return the federation directory path.

    Uses GURU_FEDERATION_DIR env var if set, otherwise ~/.guru/federation/.
    """
    import os

    env = os.environ.get("GURU_FEDERATION_DIR")
    if env:
        return Path(env)
    return Path.home() / ".guru" / "federation"
