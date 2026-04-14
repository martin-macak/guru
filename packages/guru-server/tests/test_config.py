from __future__ import annotations

import json
from pathlib import Path

from guru_core.types import GuruConfig, MatchConfig, Rule
from guru_server.config import DEFAULT_RULES, load_config, load_rules, merge_rules, resolve_config

# ---------------------------------------------------------------------------
# DEFAULT_RULES
# ---------------------------------------------------------------------------


def test_default_rules_has_one_rule():
    assert len(DEFAULT_RULES) == 1


def test_default_rules_named_default():
    assert DEFAULT_RULES[0].rule_name == "default"


def test_default_rules_glob():
    assert DEFAULT_RULES[0].match.glob == "**/*.md"


# ---------------------------------------------------------------------------
# load_rules
# ---------------------------------------------------------------------------


def test_load_rules_from_json(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text(json.dumps([{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}]))
    rules = load_rules(config_file)
    assert rules is not None
    assert len(rules) == 1
    assert rules[0].rule_name == "docs"
    assert rules[0].match.glob == "docs/**/*.md"


def test_load_rules_returns_none_for_missing_file(tmp_path: Path):
    missing = tmp_path / "nonexistent.json"
    result = load_rules(missing)
    assert result is None


# ---------------------------------------------------------------------------
# merge_rules
# ---------------------------------------------------------------------------


def test_merge_rules_local_overrides_global():
    global_rules = [Rule(rule_name="default", match=MatchConfig(glob="**/*.md"))]
    local_rules = [Rule(rule_name="default", match=MatchConfig(glob="docs/**/*.md"))]
    merged = merge_rules(global_rules, local_rules)
    assert len(merged) == 1
    assert merged[0].match.glob == "docs/**/*.md"


def test_merge_rules_local_appends_new_rules():
    global_rules = [Rule(rule_name="default", match=MatchConfig(glob="**/*.md"))]
    local_rules = [Rule(rule_name="extra", match=MatchConfig(glob="src/**/*.py"))]
    merged = merge_rules(global_rules, local_rules)
    assert len(merged) == 2
    names = {r.rule_name for r in merged}
    assert names == {"default", "extra"}


# ---------------------------------------------------------------------------
# resolve_config
# ---------------------------------------------------------------------------


def test_resolve_config_prefers_dot_guru_json(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()

    # Create .guru.json (highest priority)
    (project_root / ".guru.json").write_text(
        json.dumps([{"ruleName": "dotfile", "match": {"glob": "dotfile/**"}}])
    )
    # Also create guru.json (lower priority, should be ignored)
    (project_root / "guru.json").write_text(
        json.dumps([{"ruleName": "legacy", "match": {"glob": "legacy/**"}}])
    )

    rules = resolve_config(project_root, global_config_dir=global_dir).rules
    names = {r.rule_name for r in rules}
    assert "dotfile" in names
    assert "legacy" not in names


def test_resolve_config_prefers_guru_json(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()

    # Create guru.json (preferred over .guru/config.json)
    (project_root / "guru.json").write_text(
        json.dumps([{"ruleName": "preferred", "match": {"glob": "preferred/**"}}])
    )
    # Also create .guru/config.json (fallback, should be ignored)
    guru_dir = project_root / ".guru"
    guru_dir.mkdir()
    (guru_dir / "config.json").write_text(
        json.dumps([{"ruleName": "fallback", "match": {"glob": "fallback/**"}}])
    )

    rules = resolve_config(project_root, global_config_dir=global_dir).rules
    names = {r.rule_name for r in rules}
    assert "preferred" in names
    assert "fallback" not in names


def test_resolve_config_falls_back_to_guru_config_json(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()

    guru_dir = project_root / ".guru"
    guru_dir.mkdir()
    (guru_dir / "config.json").write_text(
        json.dumps([{"ruleName": "fallback", "match": {"glob": "fallback/**"}}])
    )

    rules = resolve_config(project_root, global_config_dir=global_dir).rules
    names = {r.rule_name for r in rules}
    assert "fallback" in names


def test_resolve_config_merges_with_global(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()

    (global_dir / "config.json").write_text(
        json.dumps([{"ruleName": "global-rule", "match": {"glob": "global/**"}}])
    )
    (project_root / ".guru.json").write_text(
        json.dumps([{"ruleName": "local-rule", "match": {"glob": "local/**"}}])
    )

    rules = resolve_config(project_root, global_config_dir=global_dir).rules
    names = {r.rule_name for r in rules}
    assert "global-rule" in names
    assert "local-rule" in names


def test_resolve_config_returns_defaults_when_no_config(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()

    cfg = resolve_config(project_root, global_config_dir=global_dir)
    assert len(cfg.rules) == 1
    assert cfg.rules[0].rule_name == "default"
    assert cfg.rules[0].match.glob == "**/*.md"


def test_load_config_legacy_array_auto_wraps(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text(json.dumps([{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}]))
    cfg = load_config(config_file)
    assert isinstance(cfg, GuruConfig)
    assert cfg.version == 1
    assert len(cfg.rules) == 1
    assert cfg.rules[0].rule_name == "docs"


def test_load_config_object_format(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [{"ruleName": "docs", "match": {"glob": "docs/**/*.md"}}],
            }
        )
    )
    cfg = load_config(config_file)
    assert cfg.version == 1
    assert cfg.rules[0].rule_name == "docs"


def test_load_config_empty_array(tmp_path: Path):
    config_file = tmp_path / "rules.json"
    config_file.write_text("[]")
    cfg = load_config(config_file)
    assert cfg.rules == []


def test_load_config_returns_none_for_missing_file(tmp_path: Path):
    assert load_config(tmp_path / "nope.json") is None
