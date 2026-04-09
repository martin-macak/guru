"""Config module — re-exported from guru_core.config (canonical source)."""
from guru_core.config import (
    DEFAULT_RULES,
    load_rules,
    merge_rules,
    resolve_config,
)

__all__ = ["DEFAULT_RULES", "load_rules", "merge_rules", "resolve_config"]
