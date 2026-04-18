"""Capability registry for the e2e test harness.

A "capability" bundles an external dependency (Neo4j today, Ollama today,
any future service) into one declarative record. Adding a new capability is
a single `_REGISTRY` entry — no Makefile or environment.py changes.

Lifecycle, driven by behave hooks in ``environment.py``:

1. ``before_all``  → :func:`activate` starts any selected capability whose
   external URI isn't already preset in ``os.environ`` and merges its env.
2. ``before_feature`` → :func:`wipe_enabled` resets per-capability state
   (e.g. ``MATCH (n) DETACH DELETE n`` on Neo4j) so features don't bleed.
3. ``before_tag`` → :func:`check_tag_gate` skips ``@real_<cap>``-tagged
   scenarios when the corresponding capability isn't active.
4. ``after_all`` → :func:`deactivate` stops capabilities we started and
   unsets any env vars we added.

Selection is via ``behave -D capabilities=neo4j,ollama`` (or ``=all``, or
the env-var fallback ``GURU_E2E_CAPABILITIES``).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_TEST_NEO4J_PORT = 17687
_TEST_NEO4J_HOME = Path(tempfile.gettempdir()) / "guru-graph-test-neo4j"
_neo4j_runtime = None


@dataclass
class Capability:
    """One external-dependency group.

    Attributes that end in ``_env`` are the public env-var contract — callers
    can preset them to signal "use this external instance, don't spawn one."
    """

    name: str
    tag: str
    env: dict[str, str]
    external_uri_env: str | None
    start: Callable[[], None] | None = None
    wipe: Callable[[], None] | None = None
    stop: Callable[[], None] | None = None
    active: bool = False
    externally_provided: bool = False


# --- neo4j capability -------------------------------------------------------


def _neo4j_start() -> None:
    global _neo4j_runtime

    from guru_graph.neo4j_process import start_neo4j
    from guru_graph.preflight import check_java_installed, check_neo4j_installed

    if _neo4j_runtime is not None:
        return

    check_java_installed()
    check_neo4j_installed()

    _TEST_NEO4J_HOME.mkdir(parents=True, exist_ok=True)
    _neo4j_runtime = start_neo4j(
        data_dir=_TEST_NEO4J_HOME / "data",
        bolt_port=_TEST_NEO4J_PORT,
        log_file=_TEST_NEO4J_HOME / "neo4j.log",
    )


def _neo4j_wipe() -> None:
    """Reset Neo4j to an empty graph with no constraints/indexes.

    Mirrors the real-Neo4j pytest fixture at
    ``packages/guru-graph/tests/conftest.py`` so BDD and pytest start from
    the same zero state.
    """
    from neo4j import GraphDatabase

    uri = os.environ["GURU_NEO4J_BOLT_URI"]
    with GraphDatabase.driver(uri, auth=None) as drv, drv.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        for rec in list(s.run("SHOW CONSTRAINTS YIELD name RETURN name")):
            s.run(f"DROP CONSTRAINT `{rec['name']}` IF EXISTS")
        for rec in list(s.run("SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name")):
            s.run(f"DROP INDEX `{rec['name']}` IF EXISTS")


def _neo4j_stop() -> None:
    global _neo4j_runtime

    from guru_graph.neo4j_process import stop_neo4j

    if _neo4j_runtime is None:
        return

    stop_neo4j(_neo4j_runtime.process)
    _neo4j_runtime = None


# --- ollama capability ------------------------------------------------------


def _ollama_start() -> None:
    """Verify a reachable Ollama — we don't spawn one ad-hoc."""
    import urllib.error
    import urllib.request

    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        urllib.request.urlopen(f"{host}/api/tags", timeout=3).read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"ollama capability requested but {host} not reachable: {exc}") from exc


# --- registry ---------------------------------------------------------------

_REGISTRY: dict[str, Capability] = {
    "neo4j": Capability(
        name="neo4j",
        tag="real_neo4j",
        env={
            "GURU_REAL_NEO4J": "1",
            "GURU_NEO4J_BOLT_URI": f"bolt://127.0.0.1:{_TEST_NEO4J_PORT}",
        },
        external_uri_env="GURU_NEO4J_BOLT_URI",
        start=_neo4j_start,
        wipe=_neo4j_wipe,
        stop=_neo4j_stop,
    ),
    "ollama": Capability(
        name="ollama",
        tag="real_ollama",
        env={"GURU_REAL_OLLAMA": "1"},
        external_uri_env="OLLAMA_HOST",
        start=_ollama_start,
        wipe=None,
        stop=None,
    ),
}

KNOWN_TAGS = {cap.tag for cap in _REGISTRY.values()}


def _parse(selector: str) -> list[Capability]:
    selector = (selector or "").strip().lower()
    if not selector:
        return []
    if selector == "all":
        return list(_REGISTRY.values())
    caps: list[Capability] = []
    for name in (s.strip() for s in selector.split(",")):
        if not name:
            continue
        if name not in _REGISTRY:
            raise ValueError(f"unknown capability {name!r}; known: {sorted(_REGISTRY)}")
        caps.append(_REGISTRY[name])
    return caps


def activate(context) -> None:
    selector = context.config.userdata.get(
        "capabilities", os.environ.get("GURU_E2E_CAPABILITIES", "")
    )
    caps = _parse(selector)
    context._capabilities = caps
    context._cap_env_keys: list[str] = []
    for cap in caps:
        cap.externally_provided = bool(
            cap.external_uri_env and os.environ.get(cap.external_uri_env)
        )
        if not cap.externally_provided and cap.start is not None:
            cap.start()
        for k, v in cap.env.items():
            # Don't clobber caller-provided overrides (e.g. CI preset URIs).
            if k not in os.environ:
                os.environ[k] = v
                context._cap_env_keys.append(k)
        cap.active = True


def deactivate(context) -> None:
    for cap in reversed(getattr(context, "_capabilities", [])):
        if cap.active and not cap.externally_provided and cap.stop is not None:
            # Teardown is best-effort — a failed stop shouldn't mask the
            # actual test result.
            with contextlib.suppress(Exception):
                cap.stop()
        cap.active = False
        cap.externally_provided = False
    for k in getattr(context, "_cap_env_keys", []):
        os.environ.pop(k, None)
    context._cap_env_keys = []


def wipe_enabled(context) -> None:
    for cap in getattr(context, "_capabilities", []):
        if cap.active and cap.wipe is not None:
            cap.wipe()


def check_tag_gate(context, tag: str) -> str | None:
    """Return a skip reason if `tag` names a capability that isn't active."""
    if tag not in KNOWN_TAGS:
        return None
    for cap in getattr(context, "_capabilities", []):
        if cap.tag == tag and cap.active:
            return None
    return f"capability for @{tag} not enabled"
