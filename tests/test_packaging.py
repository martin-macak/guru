"""Verify the root meta-package exposes console-script entry points.

Without these, `uv tool install guru` fails with
"No executables are provided by package `guru`".
"""

import importlib.metadata


def test_guru_package_has_console_scripts():
    """Root 'guru' package must declare console_scripts so uv tool install works."""
    eps = importlib.metadata.entry_points()
    # Filter for the guru distribution's console_scripts
    guru_scripts = [
        ep
        for ep in eps.select(group="console_scripts")
        if ep.dist is not None and ep.dist.name == "guru"
    ]
    script_names = {ep.name for ep in guru_scripts}
    assert "guru" in script_names, "Missing 'guru' console script in root package"
    assert "guru-server" in script_names, "Missing 'guru-server' console script in root package"
    assert "guru-mcp" in script_names, "Missing 'guru-mcp' console script in root package"
