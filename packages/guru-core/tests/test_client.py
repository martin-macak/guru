import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from guru_core.autostart import ServerStartError, _health_check, ensure_server
from guru_core.client import GuruClient


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
        fake_response = httpx.Response(
            200,
            json={
                "server_running": True,
                "document_count": 10,
                "chunk_count": 50,
                "last_indexed": None,
                "ollama_available": True,
                "model_loaded": True,
            },
        )

        async def fake_get(self, url, **kwargs):
            return fake_response

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        client = GuruClient(guru_root=guru_root)
        status = await client.status()
        assert status["server_running"] is True
        assert status["chunk_count"] == 50

    @pytest.mark.asyncio
    async def test_search(self, guru_root, monkeypatch):
        fake_response = httpx.Response(
            200,
            json=[
                {
                    "file_path": "auth.md",
                    "content": "OAuth",
                    "score": 0.9,
                    "header_breadcrumb": "Auth",
                    "chunk_level": 2,
                    "labels": "[]",
                },
            ],
        )

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

        # Mock subprocess to "start" the server (process stays alive)
        mock_popen = MagicMock()
        mock_popen.poll.return_value = None
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

        # Mock health check to succeed once the socket appears
        monkeypatch.setattr("guru_core.autostart._health_check", lambda sock_path: None)

        ensure_server(tmp_path)
        assert not pid_file.exists() or pid_file.read_text() != "99999"

    def test_health_check_failure_raises_server_start_error(self, tmp_path, monkeypatch):
        """ensure_server raises ServerStartError if health check keeps failing."""
        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        sock = guru_dir / "guru.sock"
        sock.touch()
        pid_file = guru_dir / "guru.pid"
        pid_file.write_text("99999")

        # Stale process
        monkeypatch.setattr(
            "os.kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
        )

        # Mock subprocess (process stays alive)
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: mock_proc)

        # Socket always appears immediately
        original_exists = Path.exists
        monkeypatch.setattr(
            Path,
            "exists",
            lambda self: True if self.name == "guru.sock" else original_exists(self),
        )

        # Health check always fails
        monkeypatch.setattr(
            "guru_core.autostart._health_check",
            lambda sock_path: ConnectionRefusedError("server not ready"),
        )

        with pytest.raises(ServerStartError, match="server not ready"):
            ensure_server(tmp_path, timeout=0.3)

    def test_health_check_success(self, tmp_path, monkeypatch):
        """_health_check returns None on a successful /status response."""
        fake_request = httpx.Request("GET", "http://localhost/status")
        fake_response = httpx.Response(200, json={"server_running": True}, request=fake_request)

        def fake_send(self, request, **kwargs):
            return fake_response

        monkeypatch.setattr(httpx.Client, "send", fake_send)

        result = _health_check("/fake/guru.sock")
        assert result is None

    def test_health_check_connection_error(self, tmp_path, monkeypatch):
        """_health_check returns the exception when the connection fails."""

        def fake_send(self, request, **kwargs):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx.Client, "send", fake_send)

        result = _health_check("/fake/guru.sock")
        assert isinstance(result, httpx.ConnectError)

    def test_early_exit_includes_server_log(self, tmp_path, monkeypatch):
        """When the server process exits early, the error includes server log content."""
        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        pid_file = guru_dir / "guru.pid"
        pid_file.write_text("99999")

        # No existing server
        monkeypatch.setattr(
            "os.kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
        )

        # Fake Popen that exits immediately with an error
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # process exited with code 1

        def fake_popen(*args, **kwargs):
            # Write error message to the log file (simulating stderr redirect)
            log_file = kwargs.get("stderr")
            if log_file and hasattr(log_file, "write"):
                log_file.write("OllamaNotFoundError: Ollama is not installed or not on PATH.\n")
                log_file.flush()
            return mock_proc

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        with pytest.raises(ServerStartError, match="Ollama is not installed"):
            ensure_server(tmp_path, timeout=0.5)

    def test_early_exit_detected_before_timeout(self, tmp_path, monkeypatch):
        """Early process exit is detected quickly, not after the full timeout."""
        import time

        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        pid_file = guru_dir / "guru.pid"
        pid_file.write_text("99999")

        monkeypatch.setattr(
            "os.kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
        )

        # Process that exits immediately
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1

        monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: mock_proc)

        start = time.monotonic()
        with pytest.raises(ServerStartError):
            ensure_server(tmp_path, timeout=5.0)
        elapsed = time.monotonic() - start

        # Should detect early exit well before the 5s timeout
        assert elapsed < 2.0, f"Took {elapsed:.1f}s — should detect early exit quickly"

    def test_server_log_written_to_guru_dir(self, tmp_path, monkeypatch):
        """Server stderr is redirected to .guru/server.log."""
        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        pid_file = guru_dir / "guru.pid"
        pid_file.write_text("99999")

        monkeypatch.setattr(
            "os.kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
        )

        captured_kwargs = {}

        def fake_popen(*args, **kwargs):
            captured_kwargs.update(kwargs)
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 1
            return mock_proc

        monkeypatch.setattr("subprocess.Popen", fake_popen)

        with pytest.raises(ServerStartError):
            ensure_server(tmp_path, timeout=0.3)

        # Verify stderr was directed to a file in .guru/
        stderr_target = captured_kwargs.get("stderr")
        assert stderr_target is not None
        assert stderr_target != subprocess.DEVNULL
        assert hasattr(stderr_target, "name")  # it's a file object
        assert "server.log" in stderr_target.name
