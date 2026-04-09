from __future__ import annotations

import json
from pathlib import Path

from guru_core.types import MatchConfig, Rule

DEFAULT_RULES = [
    Rule(rule_name="default", match=MatchConfig(glob="**/*.md")),
]


def load_rules(path: Path) -> list[Rule] | None:
    """Load rules from a JSON config file. Returns None if file doesn't exist."""
    if not path.is_file():
        return None
    with open(path) as f:
        data = json.load(f)
    return [Rule(**item) for item in data]


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
) -> list[Rule]:
    """Resolve configuration using the fallback chain.

    Resolution:
    1. Load ~/.config/guru/config.json as base (global)
    2. Load ./guru.json (preferred) or ./.guru/config.json (fallback) as local
    3. Merge: local rules override global by rule_name, new names appended
    4. No config anywhere -> hardcoded defaults
    """
    if global_config_dir is None:
        global_config_dir = Path.home() / ".config" / "guru"

    global_rules = load_rules(global_config_dir / "config.json")

    local_rules = load_rules(project_root / "guru.json")
    if local_rules is None:
        local_rules = load_rules(project_root / ".guru" / "config.json")

    if global_rules is None and local_rules is None:
        return list(DEFAULT_RULES)

    if global_rules is None:
        return local_rules

    if local_rules is None:
        return global_rules

    return merge_rules(global_rules, local_rules)
