from __future__ import annotations

from unittest.mock import patch

import pytest

from guru_graph.preflight import (
    JavaNotFoundError,
    Neo4jNotFoundError,
    check_java_installed,
    check_neo4j_installed,
)


def test_java_missing_raises_actionable_error():
    with patch("shutil.which", return_value=None):
        with pytest.raises(JavaNotFoundError) as exc:
            check_java_installed()
        assert "java" in str(exc.value).lower()
        assert "install" in str(exc.value).lower()


def test_java_found():
    with patch("shutil.which", return_value="/usr/bin/java"):
        check_java_installed()


def test_neo4j_missing_raises_actionable_error():
    with patch("shutil.which", return_value=None):
        with pytest.raises(Neo4jNotFoundError) as exc:
            check_neo4j_installed()
        msg = str(exc.value).lower()
        assert "neo4j" in msg
        assert "brew install neo4j" in msg or "neo4j.com/download" in msg


def test_neo4j_found():
    with patch("shutil.which", return_value="/opt/homebrew/bin/neo4j"):
        check_neo4j_installed()
