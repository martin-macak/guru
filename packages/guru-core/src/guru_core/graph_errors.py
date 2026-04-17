"""Errors raised by the graph client when the graph plugin is unreachable."""

from __future__ import annotations


class GraphUnavailable(RuntimeError):
    """Raised when the graph daemon is unreachable or incompatible."""
