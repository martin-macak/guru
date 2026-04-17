"""Guru graph plugin — see spec at docs/superpowers/specs/2026-04-17-graph-plugin-design.md."""

__all__ = ["__version__"]

try:
    from importlib.metadata import version as _version

    __version__ = _version("guru-graph")
except Exception:
    __version__ = "0.0.0+unknown"
