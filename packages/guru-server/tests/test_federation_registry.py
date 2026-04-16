from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from guru_server.federation import FederationRegistry


@pytest.fixture
def fed_dir(tmp_path: Path) -> Path:
    d = tmp_path / "federation"
    d.mkdir()
    return d


@pytest.fixture
def registry(fed_dir: Path, tmp_path: Path) -> FederationRegistry:
    socket_path = str(tmp_path / ".guru" / "guru.sock")
    return FederationRegistry(
        name="alpha",
        pid=os.getpid(),
        socket_path=socket_path,
        project_root=str(tmp_path),
        federation_dir=fed_dir,
    )


class TestDiscoveryFileWrite:
    def test_register_creates_discovery_file(self, registry: FederationRegistry, fed_dir: Path):
        registry.register()
        path = fed_dir / "alpha.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "alpha"
        assert data["pid"] == os.getpid()
        assert "socket" in data
        assert "project_root" in data
        assert "started_at" in data

    def test_register_is_atomic(self, registry: FederationRegistry, fed_dir: Path):
        """No temp file remains after registration."""
        registry.register()
        files = list(fed_dir.iterdir())
        assert len(files) == 1
        assert files[0].name == "alpha.json"

    def test_deregister_removes_file(self, registry: FederationRegistry, fed_dir: Path):
        registry.register()
        registry.deregister()
        assert not (fed_dir / "alpha.json").exists()

    def test_deregister_idempotent(self, registry: FederationRegistry, fed_dir: Path):
        """Deregistering when file already gone does not raise."""
        registry.deregister()


class TestPeerDiscovery:
    def test_list_peers_excludes_self(self, registry: FederationRegistry, fed_dir: Path):
        registry.register()
        peers = registry.list_peers()
        assert len(peers) == 0

    def test_list_peers_finds_other_server(self, registry: FederationRegistry, fed_dir: Path):
        registry.register()
        peer_data = {
            "name": "beta",
            "pid": os.getpid(),
            "socket": "/tmp/beta.sock",
            "project_root": "/tmp/beta",
            "started_at": "2026-04-16T10:00:00Z",
        }
        (fed_dir / "beta.json").write_text(json.dumps(peer_data))
        peers = registry.list_peers()
        assert len(peers) == 1
        assert peers[0]["name"] == "beta"

    def test_list_peers_skips_dead_pid(self, registry: FederationRegistry, fed_dir: Path):
        registry.register()
        peer_data = {
            "name": "dead",
            "pid": 999999999,
            "socket": "/tmp/dead.sock",
            "project_root": "/tmp/dead",
            "started_at": "2026-04-16T10:00:00Z",
        }
        (fed_dir / "dead.json").write_text(json.dumps(peer_data))
        peers = registry.list_peers()
        assert len(peers) == 0

    def test_list_peers_skips_malformed_file(self, registry: FederationRegistry, fed_dir: Path):
        registry.register()
        (fed_dir / "bad.json").write_text("not json at all")
        peers = registry.list_peers()
        assert len(peers) == 0


class TestMaintenanceSweep:
    def test_sweep_removes_dead_peer(self, registry: FederationRegistry, fed_dir: Path):
        peer_data = {
            "name": "dead",
            "pid": 999999999,
            "socket": "/tmp/dead.sock",
            "project_root": "/tmp/dead",
            "started_at": "2026-04-16T10:00:00Z",
        }
        (fed_dir / "dead.json").write_text(json.dumps(peer_data))
        registry.sweep()
        assert not (fed_dir / "dead.json").exists()

    def test_sweep_tolerates_concurrent_delete(self, registry: FederationRegistry, fed_dir: Path):
        """Sweep does not crash if file was already deleted by another server."""
        peer_data = {
            "name": "dead",
            "pid": 999999999,
            "socket": "/tmp/dead.sock",
            "project_root": "/tmp/dead",
            "started_at": "2026-04-16T10:00:00Z",
        }
        path = fed_dir / "dead.json"
        path.write_text(json.dumps(peer_data))
        path.unlink()
        registry.sweep()

    def test_sweep_preserves_alive_peer(self, registry: FederationRegistry, fed_dir: Path):
        peer_data = {
            "name": "alive",
            "pid": os.getpid(),
            "socket": "/tmp/alive.sock",
            "project_root": "/tmp/alive",
            "started_at": "2026-04-16T10:00:00Z",
        }
        (fed_dir / "alive.json").write_text(json.dumps(peer_data))
        registry.sweep()
        assert (fed_dir / "alive.json").exists()


class TestFederationDirCreation:
    def test_register_creates_federation_dir(self, tmp_path: Path):
        fed_dir = tmp_path / "nonexistent" / "federation"
        registry = FederationRegistry(
            name="alpha",
            pid=os.getpid(),
            socket_path="/tmp/alpha.sock",
            project_root=str(tmp_path),
            federation_dir=fed_dir,
        )
        registry.register()
        assert fed_dir.exists()
        assert (fed_dir / "alpha.json").exists()


class TestNameCollision:
    def test_register_warns_on_name_collision(
        self, registry: FederationRegistry, fed_dir: Path, caplog
    ):
        existing = {
            "name": "alpha",
            "pid": os.getpid(),
            "socket": "/tmp/other-alpha.sock",
            "project_root": "/tmp/other-alpha",
            "started_at": "2026-04-16T09:00:00Z",
        }
        (fed_dir / "alpha.json").write_text(json.dumps(existing))
        with caplog.at_level(logging.WARNING):
            registry.register()
        assert "collision" in caplog.text.lower() or "overwriting" in caplog.text.lower()
