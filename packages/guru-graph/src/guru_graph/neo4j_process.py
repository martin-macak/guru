"""Supervise a Neo4j subprocess.

guru-graph is the sole owner of the Neo4j process lifecycle. We run `neo4j
console` (foreground) as a child, configure the data dir via env/config,
choose a free loopback port, and probe readiness by opening a Bolt driver.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Homebrew neo4j conf source — used to stage a writable NEO4J_CONF dir.
# On non-Homebrew installs the conf dir is derived from NEO4J_HOME/conf.
_HOMEBREW_CONF_CANDIDATES = [
    Path("/opt/homebrew/Cellar"),  # Apple Silicon
    Path("/usr/local/Cellar"),  # Intel Mac
]


def _find_homebrew_neo4j_conf() -> Path | None:
    """Return the first existing neo4j conf/ dir inside any Homebrew Cellar."""
    for cellar in _HOMEBREW_CONF_CANDIDATES:
        if not cellar.is_dir():
            continue
        # e.g. /opt/homebrew/Cellar/neo4j/<version>/libexec/conf/
        for candidate in sorted(cellar.glob("neo4j/*/libexec/conf"), reverse=True):
            if candidate.is_dir():
                return candidate
    return None


def _stage_neo4j_conf(
    conf_staging_dir: Path,
    *,
    data_dir: Path,
    logs_dir: Path,
    run_dir: Path,
    bolt_port: int,
) -> None:
    """Copy Homebrew neo4j conf into *conf_staging_dir* and patch directory paths.

    Neo4j reads its configuration from the directory pointed to by the
    ``NEO4J_CONF`` environment variable (defaults to ``$NEO4J_HOME/conf``).
    Homebrew's packaged ``neo4j.conf`` hardcodes ``server.directories.data``
    and ``server.directories.logs`` to paths under ``/opt/homebrew/var/``.
    By staging our own conf dir with those paths replaced we keep all runtime
    files inside our writable ``data_dir``.
    """
    conf_staging_dir.mkdir(parents=True, exist_ok=True)
    src_conf = _find_homebrew_neo4j_conf()
    if src_conf is not None:
        logger.debug("Staging NEO4J_CONF from %s → %s", src_conf, conf_staging_dir)
        for src_file in src_conf.iterdir():
            shutil.copy2(src_file, conf_staging_dir / src_file.name)
    else:
        logger.debug("No Homebrew neo4j conf found; writing minimal neo4j.conf")

    # Keys we want to control — strip any existing declarations from the
    # copied neo4j.conf so we don't get "declared multiple times" errors.
    _KEYS_TO_OVERRIDE = {
        "server.directories.data",
        "server.directories.logs",
        "server.directories.run",
        "server.directories.transaction.logs.root",
        "dbms.security.auth_enabled",
        "server.http.enabled",
        "server.https.enabled",
        "server.bolt.listen_address",
        "server.bolt.advertised_address",
        "server.default_listen_address",
    }

    neo4j_conf = conf_staging_dir / "neo4j.conf"
    if neo4j_conf.exists():
        lines = neo4j_conf.read_text(encoding="utf-8").splitlines(keepends=True)
        filtered = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("#") or "=" not in stripped:
                filtered.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key not in _KEYS_TO_OVERRIDE:
                filtered.append(line)
            # else: drop the line — we'll re-add controlled values below
        neo4j_conf.write_text("".join(filtered), encoding="utf-8")

    overrides = "\n".join(
        [
            "",
            "# --- guru-graph runtime overrides (written by neo4j_process.py) ---",
            f"server.directories.data={data_dir}",
            f"server.directories.logs={logs_dir}",
            f"server.directories.run={run_dir}",
            f"server.directories.transaction.logs.root={data_dir / 'tx'}",
            "dbms.security.auth_enabled=false",
            # Disable HTTP/HTTPS so Jetty never tries to decompress static
            # content into the OS temp dir (which may be sandbox-restricted).
            "server.http.enabled=false",
            "server.https.enabled=false",
            # Bind Bolt to the loopback address on the caller-chosen port.
            f"server.bolt.listen_address=127.0.0.1:{bolt_port}",
            f"server.bolt.advertised_address=127.0.0.1:{bolt_port}",
            "server.default_listen_address=127.0.0.1",
            "",
        ]
    )
    with neo4j_conf.open("a") as fh:
        fh.write(overrides)
    logger.debug("Wrote NEO4J_CONF overrides to %s", neo4j_conf)


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

    Stages a private NEO4J_CONF directory so that Homebrew's neo4j binary
    picks up our writable paths instead of the hardcoded /opt/homebrew/var/…
    entries in the system neo4j.conf.  The NEO4J_CONF env var is the official
    Neo4j mechanism for pointing at an alternative conf directory.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = data_dir.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = data_dir.parent / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    conf_dir = data_dir.parent / "conf"
    _stage_neo4j_conf(
        conf_dir,
        data_dir=data_dir,
        logs_dir=logs_dir,
        run_dir=run_dir,
        bolt_port=bolt_port,
    )

    env = {
        **os.environ,
        # Point Neo4j at our staged conf dir so it ignores Homebrew's defaults.
        "NEO4J_CONF": str(conf_dir),
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
