from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import guru_graph.neo4j_process
import guru_graph.preflight

_CAPABILITIES_PATH = Path(__file__).resolve().parent / "e2e" / "features" / "capabilities.py"
_CAPABILITIES_SPEC = importlib.util.spec_from_file_location(
    "tests_e2e_features_capabilities", _CAPABILITIES_PATH
)
assert _CAPABILITIES_SPEC is not None and _CAPABILITIES_SPEC.loader is not None
capabilities = importlib.util.module_from_spec(_CAPABILITIES_SPEC)
sys.modules[_CAPABILITIES_SPEC.name] = capabilities
_CAPABILITIES_SPEC.loader.exec_module(capabilities)


def test_neo4j_capability_start_uses_native_process(monkeypatch, tmp_path):
    started: dict[str, object] = {}
    runtime = SimpleNamespace(process=MagicMock(), bolt_uri="bolt://127.0.0.1:17687")

    def fake_start_neo4j(**kwargs):
        started.update(kwargs)
        return runtime

    monkeypatch.setattr(guru_graph.preflight, "check_java_installed", lambda: None)
    monkeypatch.setattr(guru_graph.preflight, "check_neo4j_installed", lambda: None)
    monkeypatch.setattr(guru_graph.neo4j_process, "start_neo4j", fake_start_neo4j)
    monkeypatch.setattr(capabilities, "_neo4j_runtime", None, raising=False)

    capabilities._neo4j_start()

    assert started["bolt_port"] == 17687
    assert started["data_dir"].is_relative_to(capabilities._TEST_NEO4J_HOME)
    assert started["log_file"].is_relative_to(capabilities._TEST_NEO4J_HOME)
    assert capabilities._neo4j_runtime is runtime


def test_neo4j_capability_stop_uses_native_process(monkeypatch):
    import os
    import signal

    killed_pgroups: list[tuple[int, int]] = []
    proc = MagicMock()
    proc.pid = 12345
    proc.poll.return_value = None  # simulate a running process

    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed_pgroups.append((pgid, sig)))
    monkeypatch.setattr(capabilities, "_neo4j_runtime", SimpleNamespace(process=proc), raising=False)

    capabilities._neo4j_stop()

    assert capabilities._neo4j_runtime is None
    # The whole process group (identified by proc.pid) must have received SIGTERM.
    assert killed_pgroups and killed_pgroups[0] == (proc.pid, signal.SIGTERM)


@pytest.mark.parametrize("fn", [capabilities._neo4j_start, capabilities._neo4j_stop])
def test_neo4j_capability_no_longer_shells_to_docker(monkeypatch, fn):
    if fn is capabilities._neo4j_start:
        monkeypatch.setattr(
            guru_graph.neo4j_process,
            "start_neo4j",
            lambda **kwargs: SimpleNamespace(
                process=MagicMock(), bolt_uri="bolt://127.0.0.1:17687"
            ),
        )
        monkeypatch.setattr(guru_graph.preflight, "check_java_installed", lambda: None)
        monkeypatch.setattr(guru_graph.preflight, "check_neo4j_installed", lambda: None)
        monkeypatch.setattr(capabilities, "_neo4j_runtime", None, raising=False)
    else:
        monkeypatch.setattr(guru_graph.neo4j_process, "stop_neo4j", lambda process: None)
        monkeypatch.setattr(
            capabilities,
            "_neo4j_runtime",
            SimpleNamespace(process=MagicMock()),
            raising=False,
        )

    assert not hasattr(capabilities, "subprocess")
    fn()
