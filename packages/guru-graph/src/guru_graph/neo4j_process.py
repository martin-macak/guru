"""Supervise a Neo4j subprocess.

guru-graph is the sole owner of the Neo4j process lifecycle. We run `neo4j
console` (foreground) as a child, configure the data dir via env/config,
choose a free loopback port, and probe readiness by opening a Bolt driver.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class Neo4jStartError(RuntimeError):
    pass


@dataclass
class Neo4jRuntime:
    bolt_uri: str
    process: subprocess.Popen
    data_dir: Path


def start_neo4j(
    *,
    data_dir: Path,
    bolt_port: int,
    log_file: Path,
    ready_timeout_seconds: float = 60.0,
) -> Neo4jRuntime:
    """Spawn neo4j console pointed at data_dir, bind Bolt to loopback port.

    Uses environment variables to configure Neo4j at launch:
      - NEO4J_server_directories_data
      - NEO4J_server_bolt_listen__address
      - NEO4J_server_default__listen__address
      - NEO4J_dbms_security_auth__enabled = false (local UDS-guarded daemon)
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "NEO4J_server_directories_data": str(data_dir),
        "NEO4J_server_default_listen_address": "127.0.0.1",
        "NEO4J_server_bolt_listen__address": f"127.0.0.1:{bolt_port}",
        "NEO4J_server_bolt_advertised__address": f"127.0.0.1:{bolt_port}",
        "NEO4J_server_http_enabled": "false",
        "NEO4J_server_https_enabled": "false",
        "NEO4J_dbms_security_auth__enabled": "false",
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_file, "ab")  # noqa: SIM115 - intentionally held for subprocess lifetime
    proc = subprocess.Popen(
        ["neo4j", "console"],
        env=env,
        stdout=log_fd,
        stderr=log_fd,
        start_new_session=True,
    )
    bolt_uri = f"bolt://127.0.0.1:{bolt_port}"
    deadline = time.monotonic() + ready_timeout_seconds
    last_err: Exception | None = None
    from neo4j import GraphDatabase  # local import to keep import-time light

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise Neo4jStartError(
                f"neo4j exited during startup (code={proc.returncode}); see {log_file}"
            )
        try:
            driver = GraphDatabase.driver(bolt_uri, auth=None, max_connection_lifetime=60)
            driver.verify_connectivity()
            driver.close()
            logger.info("neo4j ready at %s", bolt_uri)
            return Neo4jRuntime(bolt_uri=bolt_uri, process=proc, data_dir=data_dir)
        except Exception as e:
            last_err = e
            time.sleep(0.5)

    stop_neo4j(proc)
    raise Neo4jStartError(
        f"neo4j did not become ready within {ready_timeout_seconds}s. "
        f"Last error: {last_err!r}. See {log_file}"
    )


def stop_neo4j(proc: subprocess.Popen, *, grace_seconds: float = 15.0) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        logger.warning("neo4j did not exit in %ss; sending SIGKILL", grace_seconds)
        proc.kill()
        proc.wait()
