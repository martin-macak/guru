import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from guru_core.client import GuruClient
from guru_core.autostart import ensure_server, ServerStartError


class TestGuruClient:
    @pytest.fixture
    def guru_root(self, tmp_path):
        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        sock = guru_dir / "guru.sock"
        sock.touch()  # Fake socket file
        pid = guru_dir / "guru.pid"
        pid.write_text("12345")
        return tmp_path

    def test_init_sets_socket_path(self, guru_root):
        client = GuruClient(guru_root=guru_root)
        assert client.socket_path == str(guru_root / ".guru" / "guru.sock")

    @pytest.mark.asyncio
    async def test_status(self, guru_root, monkeypatch):
        fake_response = httpx.Response(200, json={
            "server_running": True,
            "document_count": 10,
            "chunk_count": 50,
            "last_indexed": None,
            "ollama_available": True,
            "model_loaded": True,
        })

        async def fake_get(self, url, **kwargs):
            return fake_response

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        client = GuruClient(guru_root=guru_root)
        status = await client.status()
        assert status["server_running"] is True
        assert status["chunk_count"] == 50

    @pytest.mark.asyncio
    async def test_search(self, guru_root, monkeypatch):
        fake_response = httpx.Response(200, json=[
            {"file_path": "auth.md", "content": "OAuth", "score": 0.9,
             "header_breadcrumb": "Auth", "chunk_level": 2, "labels": "[]"},
        ])

        async def fake_post(self, url, **kwargs):
            return fake_response

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        client = GuruClient(guru_root=guru_root)
        results = await client.search("authentication")
        assert len(results) == 1
        assert results[0]["file_path"] == "auth.md"


class TestEnsureServer:
    def test_server_already_running(self, tmp_path, monkeypatch):
        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        sock = guru_dir / "guru.sock"
        sock.touch()
        pid_file = guru_dir / "guru.pid"
        pid_file.write_text("12345")

        # Mock os.kill to succeed (process exists)
        monkeypatch.setattr("os.kill", lambda pid, sig: None)

        ensure_server(tmp_path)  # Should not raise

    def test_stale_pid_triggers_cleanup(self, tmp_path, monkeypatch):
        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        sock = guru_dir / "guru.sock"
        sock.touch()
        pid_file = guru_dir / "guru.pid"
        pid_file.write_text("99999")

        # Mock os.kill to fail (process doesn't exist)
        def fake_kill(pid, sig):
            raise ProcessLookupError()

        monkeypatch.setattr("os.kill", fake_kill)

        # Mock subprocess to "start" the server
        mock_popen = MagicMock()
        monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: mock_popen)

        # Mock socket check to succeed after start
        call_count = 0
        original_exists = Path.exists
        def fake_exists(self):
            nonlocal call_count
            if self.name == "guru.sock":
                call_count += 1
                return call_count > 1  # Fail first, succeed second
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", fake_exists)

        ensure_server(tmp_path)
        assert not pid_file.exists() or pid_file.read_text() != "99999"
