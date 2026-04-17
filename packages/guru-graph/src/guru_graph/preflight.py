"""Preflight checks run during guru-graph daemon startup.

Mirrors guru-server's Ollama preflight pattern. Hard errors on missing deps
with clear install instructions.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)


class JavaNotFoundError(RuntimeError):
    pass


class Neo4jNotFoundError(RuntimeError):
    pass


def check_java_installed() -> None:
    if shutil.which("java") is None:
        raise JavaNotFoundError(
            "Java is not installed or not on PATH. Neo4j requires Java 17+.\n"
            "Install it with: brew install openjdk@17 (macOS) "
            "or apt install openjdk-17-jre (Debian/Ubuntu).\n"
            "After install, run: java -version (should report 17+)."
        )
    # Verify that the installed Java meets the minimum version requirement (17+).
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # `java -version` writes to stderr
        version_output = result.stderr or result.stdout
        # Parse the major version from output like:
        # openjdk version "17.0.2" ...  or  java version "1.8.0_321"
        match = re.search(r'"(?:(\d+)\.)?(\d+)', version_output)
        if match:
            major = int(match.group(1) or match.group(2))
            # For Java 1.x format (Java 8 and below), group(1) is "1" and group(2) is the minor
            if major == 1:
                major = int(match.group(2))
            if major < 17:
                raise JavaNotFoundError(
                    f"Java {major} detected, but Neo4j requires Java 17+.\n"
                    "Install it with: brew install openjdk@17 (macOS) "
                    "or apt install openjdk-17-jre (Debian/Ubuntu).\n"
                    "After install, run: java -version (should report 17+)."
                )
    except FileNotFoundError as e:
        raise JavaNotFoundError(
            "Java is not installed or not on PATH. Neo4j requires Java 17+.\n"
            "Install it with: brew install openjdk@17 (macOS) "
            "or apt install openjdk-17-jre (Debian/Ubuntu).\n"
            "After install, run: java -version (should report 17+)."
        ) from e
    except subprocess.TimeoutExpired:
        logger.warning("java -version timed out; skipping version check")
    logger.info("Java found on PATH")


def check_neo4j_installed() -> None:
    if shutil.which("neo4j") is None:
        raise Neo4jNotFoundError(
            "Neo4j is not installed or not on PATH.\n"
            "Install it with: brew install neo4j (macOS) "
            "or see https://neo4j.com/download/ for other platforms.\n"
            "Requires Java 17+."
        )
    logger.info("Neo4j found on PATH")
