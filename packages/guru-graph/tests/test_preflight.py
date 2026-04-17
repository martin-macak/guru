from __future__ import annotations

import subprocess
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


def _make_version_result(version_str: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["java", "-version"], returncode=0, stdout="", stderr=version_str
    )


def test_java_found_version_17():
    version_output = 'openjdk version "17.0.2" 2022-01-18'
    with (
        patch("shutil.which", return_value="/usr/bin/java"),
        patch("subprocess.run", return_value=_make_version_result(version_output)),
    ):
        check_java_installed()  # should not raise


def test_java_found_version_21():
    version_output = 'openjdk version "21.0.1" 2023-10-17'
    with (
        patch("shutil.which", return_value="/usr/bin/java"),
        patch("subprocess.run", return_value=_make_version_result(version_output)),
    ):
        check_java_installed()  # should not raise


def test_java_old_version_raises():
    version_output = 'java version "1.8.0_321" 2022-01-18'
    with (
        patch("shutil.which", return_value="/usr/bin/java"),
        patch("subprocess.run", return_value=_make_version_result(version_output)),
        pytest.raises(JavaNotFoundError) as exc,
    ):
        check_java_installed()
    assert "8" in str(exc.value) or "detected" in str(exc.value).lower()
    assert "17+" in str(exc.value)


def test_java_version_11_raises():
    version_output = 'openjdk version "11.0.14" 2022-01-18'
    with (
        patch("shutil.which", return_value="/usr/bin/java"),
        patch("subprocess.run", return_value=_make_version_result(version_output)),
        pytest.raises(JavaNotFoundError) as exc,
    ):
        check_java_installed()
    assert "17+" in str(exc.value)


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
