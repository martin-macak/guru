from __future__ import annotations

import logging

import pytest

from guru_server.main import _resolve_cache_db_path


class TestMainArgParsing:
    @pytest.fixture(autouse=True)
    def reset_root_logger(self):
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        yield
        root.handlers = original_handlers
        root.level = original_level

    def test_parse_log_level_flag(self):
        from guru_server.main import _parse_args

        args = _parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_parse_log_file_flag(self):
        from guru_server.main import _parse_args

        args = _parse_args(["--log-file", "/tmp/test.log"])
        assert args.log_file == "/tmp/test.log"

    def test_default_log_level_is_none(self):
        from guru_server.main import _parse_args

        args = _parse_args([])
        assert args.log_level is None

    def test_default_log_file_is_none(self):
        from guru_server.main import _parse_args

        args = _parse_args([])
        assert args.log_file is None


def test_resolve_cache_db_path_uses_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(tmp_path / "my_cache.db"))
    result = _resolve_cache_db_path()
    assert result == tmp_path / "my_cache.db"


def test_resolve_cache_db_path_uses_platformdirs_when_no_env(monkeypatch):
    monkeypatch.delenv("GURU_EMBED_CACHE_PATH", raising=False)
    result = _resolve_cache_db_path()
    assert "guru" in str(result).lower()
    assert str(result).endswith("embeddings.db")


class TestMainFederationLifecycle:
    """Tests that main() registers/deregisters a federation discovery file."""

    @pytest.fixture()
    def project_dir(self, tmp_path):
        """A minimal project directory with .guru/ and a .guru.json config."""
        guru_dir = tmp_path / ".guru"
        guru_dir.mkdir()
        config_file = tmp_path / ".guru.json"
        config_file.write_text('{"version": 1, "name": "test-project", "rules": []}')
        return tmp_path

    @pytest.fixture()
    def fed_dir(self, tmp_path):
        """A separate temp directory to use as the federation directory."""
        d = tmp_path / "federation"
        d.mkdir()
        return d

    def _run_main_with_mocks(self, monkeypatch, project_dir, fed_dir):
        """Helper: run main() with all external side-effects mocked out."""
        monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
        monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))
        monkeypatch.setenv("GURU_FEDERATION_DIR", str(fed_dir))

        import guru_server.main as main_mod

        monkeypatch.setattr(main_mod, "check_ollama_installed", lambda: None)
        monkeypatch.setattr(main_mod, "start_ollama_serve", lambda: None)
        monkeypatch.setattr(main_mod, "stop_ollama_serve", lambda proc: None)
        monkeypatch.setattr(main_mod, "check_model_available", lambda model: None)
        monkeypatch.setattr(main_mod.uvicorn, "run", lambda app, **kwargs: None)

        from guru_server.main import main

        main([])

    def test_discovery_file_created_on_startup(self, monkeypatch, project_dir, fed_dir):
        """main() must write a discovery file in the federation directory."""
        captured: list[dict] = []

        import guru_server.main as main_mod

        def patched_run(app, **kwargs):
            # At the time uvicorn.run is called, the discovery file must exist
            import json

            files = list(fed_dir.glob("*.json"))
            assert files, "Expected a discovery file in the federation directory"
            data = json.loads(files[0].read_text())
            captured.append(data)

        monkeypatch.setenv("GURU_PROJECT_ROOT", str(project_dir))
        monkeypatch.setenv("GURU_EMBED_CACHE_PATH", str(project_dir / "cache.db"))
        monkeypatch.setenv("GURU_FEDERATION_DIR", str(fed_dir))

        monkeypatch.setattr(main_mod, "check_ollama_installed", lambda: None)
        monkeypatch.setattr(main_mod, "start_ollama_serve", lambda: None)
        monkeypatch.setattr(main_mod, "stop_ollama_serve", lambda proc: None)
        monkeypatch.setattr(main_mod, "check_model_available", lambda model: None)
        monkeypatch.setattr(main_mod.uvicorn, "run", patched_run)

        from guru_server.main import main

        main([])

        assert captured, "uvicorn.run was not called"
        assert captured[0]["name"] == "test-project"
        assert "socket" in captured[0]
        assert "pid" in captured[0]

    def test_discovery_file_removed_on_shutdown(self, monkeypatch, project_dir, fed_dir):
        """main() must remove the discovery file from the federation directory after uvicorn exits."""
        self._run_main_with_mocks(monkeypatch, project_dir, fed_dir)

        remaining = list(fed_dir.glob("*.json"))
        assert not remaining, f"Expected no discovery files after shutdown, found: {remaining}"
