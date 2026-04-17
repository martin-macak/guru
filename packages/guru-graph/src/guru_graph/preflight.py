"""Preflight checks run during guru-graph daemon startup.

Mirrors guru-server's Ollama preflight pattern. Hard errors on missing deps
with clear install instructions.
"""

from __future__ import annotations

import logging
import shutil

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
