# Server Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add proper Python logging infrastructure to the guru server so errors are always visible and diagnosable.

**Architecture:** A shared `setup_logging()` function in guru-core configures Python's standard `logging` module with a stderr handler (always) and an optional `RotatingFileHandler`. The server process owns its logging via CLI args (`--log-level`, `--log-file`). Autostart passes these args to the daemon subprocess. The CLI gains `--foreground` mode for interactive debugging.

**Tech Stack:** Python `logging` (stdlib), `logging.handlers.RotatingFileHandler`, `argparse`, `click`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `packages/guru-core/src/guru_core/log.py` | New — `setup_logging()` function |
| `packages/guru-core/tests/test_log.py` | New — tests for `setup_logging()` |
| `packages/guru-core/src/guru_core/client.py` | Add DEBUG logging to HTTP calls |
| `packages/guru-core/src/guru_core/autostart.py` | Pass `--log-file`/`--log-level` args, append-mode stderr |
| `packages/guru-core/tests/test_client.py` | Update autostart tests |
| `packages/guru-server/src/guru_server/main.py` | Parse CLI args, call `setup_logging()`, configure uvicorn |
| `packages/guru-server/src/guru_server/startup.py` | Add INFO logging |
| `packages/guru-server/src/guru_server/embedding.py` | Add DEBUG/ERROR logging |
| `packages/guru-server/src/guru_server/storage.py` | Add WARNING/ERROR logging |
| `packages/guru-server/src/guru_server/api/index.py` | Add INFO/ERROR logging with timing |
| `packages/guru-cli/src/guru_cli/cli.py` | Add `--foreground`, `--log-file`, `--log-level` flags |

---

### Task 1: Create `setup_logging()` in guru-core

**Files:**
- Create: `packages/guru-core/src/guru_core/log.py`
- Create: `packages/guru-core/tests/test_log.py`

- [ ] **Step 1: Write failing tests**

Create `packages/guru-core/tests/test_log.py`:

```python
from __future__ import annotations

import logging

import pytest

from guru_core.log import setup_logging

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class TestSetupLogging:
    @pytest.fixture(autouse=True)
    def reset_root_logger(self):
        """Remove all handlers added during a test."""
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        yield
        root.handlers = original_handlers
        root.level = original_level

    def test_default_level_is_info(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_level_override(self):
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_stderr_handler_always_added(self):
        setup_logging()
        root = logging.getLogger()
        stream_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_file_handler_added_when_log_file_provided(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        setup_logging(log_file=log_file)
        root = logging.getLogger()
        from logging.handlers import RotatingFileHandler
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 10 * 1024 * 1024
        assert file_handlers[0].backupCount == 3

    def test_no_file_handler_when_log_file_not_provided(self):
        setup_logging()
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_log_format(self):
        setup_logging()
        root = logging.getLogger()
        handler = root.handlers[-1]
        assert handler.formatter._fmt == LOG_FORMAT

    def test_writes_to_log_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logging(level="INFO", log_file=str(log_file))
        logger = logging.getLogger("test.writes")
        logger.info("hello from test")
        # Flush handlers
        for h in logging.getLogger().handlers:
            h.flush()
        content = log_file.read_text()
        assert "hello from test" in content

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("GURU_LOG_LEVEL", "WARNING")
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_explicit_level_overrides_env_var(self, monkeypatch):
        monkeypatch.setenv("GURU_LOG_LEVEL", "WARNING")
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_idempotent_no_duplicate_handlers(self):
        setup_logging()
        setup_logging()
        root = logging.getLogger()
        stream_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-core/tests/test_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'guru_core.log'`

- [ ] **Step 3: Write implementation**

Create `packages/guru-core/src/guru_core/log.py`:

```python
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_GURU_HANDLER_ATTR = "_guru_logging"


def setup_logging(
    level: str | None = None,
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configure logging for all guru packages.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
               Falls back to GURU_LOG_LEVEL env var, then INFO.
        log_file: Optional path for a RotatingFileHandler.
        max_bytes: Max log file size before rotation (default 10MB).
        backup_count: Number of rotated files to keep (default 3).
    """
    root = logging.getLogger()

    # Remove any handlers we previously added (idempotent)
    root.handlers = [h for h in root.handlers if not getattr(h, _GURU_HANDLER_ATTR, False)]

    # Resolve level: explicit arg > env var > INFO
    if level is None:
        level = os.environ.get("GURU_LOG_LEVEL", "INFO")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Always add stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    setattr(stderr_handler, _GURU_HANDLER_ATTR, True)
    root.addHandler(stderr_handler)

    # Optionally add rotating file handler
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        setattr(file_handler, _GURU_HANDLER_ATTR, True)
        root.addHandler(file_handler)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-core/tests/test_log.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/guru-core/src/guru_core/log.py packages/guru-core/tests/test_log.py
git commit -m "feat(guru-core): Add setup_logging() with stderr and rotating file handler"
```

---

### Task 2: Add CLI args to `guru-server` and integrate logging

**Files:**
- Modify: `packages/guru-server/src/guru_server/main.py`
- Modify: `packages/guru-server/tests/` (if existing main tests need updating)

- [ ] **Step 1: Write failing test**

Add to a new file `packages/guru-server/tests/test_main.py`:

```python
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-server/tests/test_main.py -v`
Expected: FAIL — `ImportError: cannot import name '_parse_args' from 'guru_server.main'`

- [ ] **Step 3: Add arg parsing and logging to main.py**

Modify `packages/guru-server/src/guru_server/main.py`. The full new content:

```python
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn

from guru_core.log import LOG_FORMAT, DATE_FORMAT, setup_logging
from guru_server.app import create_app
from guru_server.config import resolve_config
from guru_server.embedding import OllamaEmbedder
from guru_server.startup import (
    check_model_available,
    check_ollama_installed,
    start_ollama_serve,
    stop_ollama_serve,
)
from guru_server.storage import VectorStore

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guru knowledge-base server")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Log level (default: INFO, overrides GURU_LOG_LEVEL env var)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Path to log file (enables rotating file handler)",
    )
    return parser.parse_args(argv)


def _uvicorn_log_config(formatter_fmt: str, date_fmt: str) -> dict:
    """Build a uvicorn log_config that reuses our log format."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"fmt": formatter_fmt, "datefmt": date_fmt},
            "access": {"fmt": formatter_fmt, "datefmt": date_fmt},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }


def main():
    args = _parse_args()
    setup_logging(level=args.log_level, log_file=args.log_file)

    project_root = os.environ.get("GURU_PROJECT_ROOT", os.getcwd())
    guru_dir = Path(project_root) / ".guru"

    if not guru_dir.is_dir():
        logger.error("%s does not exist. Run `guru init` first.", guru_dir)
        sys.exit(1)

    logger.info("Starting guru-server (project_root=%s)", project_root)

    # Preflight checks + startup
    check_ollama_installed()
    ollama_proc = start_ollama_serve()
    try:
        check_model_available("nomic-embed-text")

        config = resolve_config(project_root=Path(project_root))
        store = VectorStore(db_path=str(guru_dir / "db"))
        embedder = OllamaEmbedder()

        app = create_app(
            store=store,
            embedder=embedder,
            config=config,
            project_root=project_root,
        )

        socket_path = str(guru_dir / "guru.sock")
        pid_path = guru_dir / "guru.pid"

        pid_path.write_text(str(os.getpid()))
        logger.info("Listening on %s (PID %d)", socket_path, os.getpid())

        try:
            uvicorn.run(
                app,
                uds=socket_path,
                log_config=_uvicorn_log_config(LOG_FORMAT, DATE_FORMAT),
            )
        finally:
            pid_path.unlink(missing_ok=True)
            Path(socket_path).unlink(missing_ok=True)
            logger.info("Server shut down")
    finally:
        stop_ollama_serve(ollama_proc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-server/tests/test_main.py -v`
Expected: all PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add packages/guru-server/src/guru_server/main.py packages/guru-server/tests/test_main.py
git commit -m "feat(guru-server): Add --log-level/--log-file args and integrate setup_logging()"
```

---

### Task 3: Update autostart to pass logging args

**Files:**
- Modify: `packages/guru-core/src/guru_core/autostart.py`
- Modify: `packages/guru-core/tests/test_client.py` (autostart tests)

- [ ] **Step 1: Write failing test**

Add to `packages/guru-core/tests/test_client.py` in `TestEnsureServer`:

```python
def test_passes_log_file_arg_to_server(self, tmp_path, monkeypatch):
    """ensure_server passes --log-file pointing to .guru/server.log."""
    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    pid_file = guru_dir / "guru.pid"
    pid_file.write_text("99999")

    monkeypatch.setattr(
        "os.kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
    )

    captured_args = {}

    def fake_popen(*args, **kwargs):
        captured_args["cmd"] = args[0] if args else kwargs.get("args")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        return mock_proc

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    original_exists = Path.exists
    call_count = 0

    def fake_exists(self):
        nonlocal call_count
        if self.name == "guru.sock":
            call_count += 1
            return call_count > 1
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr("guru_core.autostart._health_check", lambda sock_path: None)

    ensure_server(tmp_path)

    cmd = captured_args["cmd"]
    assert "--log-file" in cmd
    log_file_idx = cmd.index("--log-file")
    log_file_path = cmd[log_file_idx + 1]
    assert log_file_path == str(guru_dir / "server.log")

def test_passes_log_level_from_env(self, tmp_path, monkeypatch):
    """ensure_server forwards GURU_LOG_LEVEL as --log-level arg."""
    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    pid_file = guru_dir / "guru.pid"
    pid_file.write_text("99999")

    monkeypatch.setattr(
        "os.kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
    )
    monkeypatch.setenv("GURU_LOG_LEVEL", "DEBUG")

    captured_args = {}

    def fake_popen(*args, **kwargs):
        captured_args["cmd"] = args[0] if args else kwargs.get("args")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        return mock_proc

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    original_exists = Path.exists
    call_count = 0

    def fake_exists(self):
        nonlocal call_count
        if self.name == "guru.sock":
            call_count += 1
            return call_count > 1
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr("guru_core.autostart._health_check", lambda sock_path: None)

    ensure_server(tmp_path)

    cmd = captured_args["cmd"]
    assert "--log-level" in cmd
    level_idx = cmd.index("--log-level")
    assert cmd[level_idx + 1] == "DEBUG"

def test_stderr_redirected_in_append_mode(self, tmp_path, monkeypatch):
    """Daemon stderr goes to server.log in append mode (not truncate)."""
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
        mock_proc.poll.return_value = None
        return mock_proc

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    original_exists = Path.exists
    call_count = 0

    def fake_exists(self):
        nonlocal call_count
        if self.name == "guru.sock":
            call_count += 1
            return call_count > 1
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr("guru_core.autostart._health_check", lambda sock_path: None)

    ensure_server(tmp_path)

    stderr_target = captured_kwargs.get("stderr")
    assert stderr_target is not None
    assert hasattr(stderr_target, "mode")
    assert "a" in stderr_target.mode
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-core/tests/test_client.py::TestEnsureServer::test_passes_log_file_arg_to_server packages/guru-core/tests/test_client.py::TestEnsureServer::test_passes_log_level_from_env packages/guru-core/tests/test_client.py::TestEnsureServer::test_stderr_redirected_in_append_mode -v`
Expected: FAIL

- [ ] **Step 3: Update autostart.py**

Modify `packages/guru-core/src/guru_core/autostart.py` — full `ensure_server` function. Key changes:
- Build command list with `--log-file` and `--log-level` args
- Open stderr log file in append mode (`"a"`)

```python
def ensure_server(guru_root: Path, timeout: float = 5.0) -> None:
    """Ensure the guru server is running."""
    guru_dir = guru_root / ".guru"
    pid_file = guru_dir / "guru.pid"
    sock_file = guru_dir / "guru.sock"

    # Check if already running
    if pid_file.exists() and sock_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if _is_pid_alive(pid):
                return
        except (ValueError, OSError):
            pass

    _cleanup_stale(guru_dir)

    env = os.environ.copy()
    env["GURU_PROJECT_ROOT"] = str(guru_root)

    # Build server command with logging args
    cmd = ["guru-server", "--log-file", str(guru_dir / "server.log")]
    log_level = os.environ.get("GURU_LOG_LEVEL")
    if log_level:
        cmd.extend(["--log-level", log_level])

    # Redirect stderr to server.log in append mode as safety net for early crashes
    log_path = guru_dir / "server.log"
    log_file = open(log_path, "a")  # noqa: SIM115

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
        start_new_session=True,
        env=env,
    )

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_file.close()
            log_tail = _read_log_tail(log_path)
            raise ServerStartError(
                f"guru-server exited with code {proc.returncode}.\n{log_tail}"
            )

        if sock_file.exists():
            last_error = _health_check(str(sock_file))
            if last_error is None:
                log_file.close()
                return
        time.sleep(0.1)

    log_file.close()
    log_tail = _read_log_tail(log_path)
    detail = f": {last_error}" if last_error is not None else ""
    raise ServerStartError(
        f"guru-server did not start within {timeout}s{detail}.\n{log_tail}"
    )
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest packages/guru-core/tests/test_client.py::TestEnsureServer::test_passes_log_file_arg_to_server packages/guru-core/tests/test_client.py::TestEnsureServer::test_passes_log_level_from_env packages/guru-core/tests/test_client.py::TestEnsureServer::test_stderr_redirected_in_append_mode -v`
Expected: PASS

- [ ] **Step 5: Fix any broken existing autostart tests**

Some existing tests (e.g., `test_server_log_written_to_guru_dir`) may need updating because the `open` mode changed from `"w"` to `"a"` and the subprocess command now includes extra args. Run the full autostart test class and fix as needed:

Run: `uv run pytest packages/guru-core/tests/test_client.py::TestEnsureServer -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add packages/guru-core/src/guru_core/autostart.py packages/guru-core/tests/test_client.py
git commit -m "feat(guru-core): Pass --log-file/--log-level to daemon, use append mode"
```

---

### Task 4: Add logging to server modules

**Files:**
- Modify: `packages/guru-server/src/guru_server/api/index.py`
- Modify: `packages/guru-server/src/guru_server/embedding.py`
- Modify: `packages/guru-server/src/guru_server/storage.py`
- Modify: `packages/guru-server/src/guru_server/startup.py`

These are additive changes — adding `logger` calls to existing code. No behavior changes, so existing tests remain valid. Test by verifying all existing tests still pass.

- [ ] **Step 1: Add logging to `api/index.py`**

Add at top of file:

```python
import logging
import time

logger = logging.getLogger(__name__)
```

Add at start of `trigger_index()`:

```python
logger.info("Indexing requested (path=%s)", body.path or "project root")
t0 = time.monotonic()
```

After the `if all_chunks:` block, before the return:

```python
elapsed = time.monotonic() - t0
logger.info(
    "Indexing complete: %d chunks from %d documents in %.1fs",
    len(all_chunks),
    len({c.file_path for c in all_chunks}),
    elapsed,
)
```

Wrap `embed_batch` in a try/except to log errors:

```python
try:
    vectors = await embedder.embed_batch(texts)
except Exception:
    logger.exception("Embedding failed during indexing")
    raise
```

- [ ] **Step 2: Add logging to `embedding.py`**

Add at top:

```python
import logging
import time

logger = logging.getLogger(__name__)
```

In `embed()`, around the HTTP call:

```python
async def embed(self, text: str) -> list[float]:
    logger.debug("Embedding text (length=%d)", len(text))
    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=30.0,
        )
    if response.status_code != 200:
        logger.error("Ollama embedding failed (%d): %s", response.status_code, response.text)
        raise EmbeddingError(
            f"Ollama embedding failed ({response.status_code}): {response.text}"
        )
    logger.debug("Embedding complete in %.2fs", time.monotonic() - t0)
    return response.json()["embedding"]
```

Apply the same pattern to `embed_batch()`:

```python
async def embed_batch(self, texts: list[str]) -> list[list[float]]:
    logger.debug("Embedding batch of %d texts", len(texts))
    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        results = []
        for i, text in enumerate(texts):
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )
            if response.status_code != 200:
                logger.error(
                    "Ollama embedding failed for text %d/%d (%d): %s",
                    i + 1, len(texts), response.status_code, response.text,
                )
                raise EmbeddingError(
                    f"Ollama embedding failed ({response.status_code}): {response.text}"
                )
            results.append(response.json()["embedding"])
    logger.debug("Batch embedding complete: %d texts in %.2fs", len(texts), time.monotonic() - t0)
    return results
```

- [ ] **Step 3: Add logging to `storage.py`**

Add at top:

```python
import logging

logger = logging.getLogger(__name__)
```

In `_get_table()`:

```python
def _get_table(self):
    if self._table is None:
        try:
            self._table = self.db.open_table(TABLE_NAME)
        except FileNotFoundError:
            logger.warning("Table '%s' not found (no data indexed yet)", TABLE_NAME)
            return None
        except Exception as exc:
            msg = str(exc).lower()
            if any(phrase in msg for phrase in _TABLE_NOT_FOUND_PHRASES):
                logger.warning("Table '%s' not found: %s", TABLE_NAME, exc)
                return None
            raise
    return self._table
```

In `_parse_json_list()`:

```python
def _parse_json_list(value: str) -> list:
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse JSON list: %.100s", value)
        return []
```

In `_parse_json_dict()`:

```python
def _parse_json_dict(value: str) -> dict:
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse JSON dict: %.100s", value)
        return {}
```

- [ ] **Step 4: Add logging to `startup.py`**

Add at top:

```python
import logging

logger = logging.getLogger(__name__)
```

In `check_ollama_installed()`:

```python
def check_ollama_installed() -> None:
    if shutil.which("ollama") is None:
        raise OllamaNotFoundError(...)
    logger.info("Ollama found on PATH")
```

In `check_model_available()`, after the check:

```python
    logger.info("Model '%s' is available", model)
```

In `start_ollama_serve()`:

```python
def start_ollama_serve() -> subprocess.Popen | None:
    try:
        subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True, timeout=5)
        logger.info("Ollama is already running")
        return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    logger.info("Starting ollama serve")
    return subprocess.Popen(...)
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all pass (logging additions don't change behavior)

- [ ] **Step 6: Commit**

```bash
git add packages/guru-server/src/guru_server/api/index.py packages/guru-server/src/guru_server/embedding.py packages/guru-server/src/guru_server/storage.py packages/guru-server/src/guru_server/startup.py
git commit -m "feat(guru-server): Add structured logging to all server modules"
```

---

### Task 5: Add DEBUG logging to guru-core client

**Files:**
- Modify: `packages/guru-core/src/guru_core/client.py`

- [ ] **Step 1: Write failing test**

Add to `packages/guru-core/tests/test_client.py` in `TestGuruClient`:

```python
@pytest.mark.asyncio
async def test_post_logs_request_at_debug(self, guru_root, monkeypatch, caplog):
    """_post logs HTTP method, path, and response status at DEBUG level."""
    fake_response = httpx.Response(200, json={"indexed": 5, "documents": 2})

    async def fake_post(self, url, **kwargs):
        return fake_response

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = GuruClient(guru_root=guru_root)
    with caplog.at_level(logging.DEBUG, logger="guru_core.client"):
        await client.trigger_index()

    assert any("POST /index" in r.message for r in caplog.records)
    assert any("200" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/guru-core/tests/test_client.py::TestGuruClient::test_post_logs_request_at_debug -v`
Expected: FAIL — no log records matching

- [ ] **Step 3: Add logging to client.py**

Add at top of `client.py`:

```python
import logging

logger = logging.getLogger(__name__)
```

Update `_get` and `_post` to log:

```python
async def _get(self, path: str) -> dict | list:
    async with httpx.AsyncClient(
        transport=self._transport(), timeout=self._timeout
    ) as client:
        logger.debug("GET %s", path)
        resp = await client.get(f"http://localhost{path}")
        logger.debug("GET %s -> %d", path, resp.status_code)
        if resp.is_error:
            resp.raise_for_status()
        return resp.json()

async def _post(self, path: str, json: dict) -> dict | list:
    async with httpx.AsyncClient(
        transport=self._transport(), timeout=self._timeout
    ) as client:
        logger.debug("POST %s", path)
        resp = await client.post(f"http://localhost{path}", json=json)
        logger.debug("POST %s -> %d", path, resp.status_code)
        if resp.is_error:
            resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/guru-core/tests/test_client.py::TestGuruClient::test_post_logs_request_at_debug -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/guru-core/src/guru_core/client.py packages/guru-core/tests/test_client.py
git commit -m "feat(guru-core): Add DEBUG logging to GuruClient HTTP calls"
```

---

### Task 6: Add `--foreground`, `--log-file`, `--log-level` to CLI

**Files:**
- Modify: `packages/guru-cli/src/guru_cli/cli.py`

- [ ] **Step 1: Write failing test**

Create `packages/guru-cli/tests/test_cli_server.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from guru_cli.cli import cli


class TestServerStartFlags:
    def test_foreground_flag_accepted(self):
        runner = CliRunner()
        with patch("guru_cli.cli.find_guru_root") as mock_find, \
             patch("guru_cli.cli._run_foreground") as mock_fg:
            mock_find.return_value = "/tmp/fake"
            result = runner.invoke(cli, ["server", "start", "--foreground"])
            assert result.exit_code == 0 or mock_fg.called

    def test_log_level_flag_accepted(self):
        runner = CliRunner()
        with patch("guru_cli.cli.find_guru_root") as mock_find, \
             patch("guru_cli.cli.ensure_server"):
            mock_find.return_value = "/tmp/fake"
            result = runner.invoke(cli, ["server", "start", "--log-level", "DEBUG"])
            # Should not error on unknown flag
            assert "no such option" not in (result.output or "").lower()

    def test_log_file_flag_accepted(self):
        runner = CliRunner()
        with patch("guru_cli.cli.find_guru_root") as mock_find, \
             patch("guru_cli.cli.ensure_server"):
            mock_find.return_value = "/tmp/fake"
            result = runner.invoke(cli, ["server", "start", "--log-file", "/tmp/test.log"])
            assert "no such option" not in (result.output or "").lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/guru-cli/tests/test_cli_server.py -v`
Expected: FAIL

- [ ] **Step 3: Update the `server start` command**

Modify `packages/guru-cli/src/guru_cli/cli.py`. Replace the `server_start` function:

```python
@server.command("start")
@click.option("--foreground", is_flag=True, help="Run in foreground (no daemonization)")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False), default=None, help="Log level")
@click.option("--log-file", type=click.Path(), default=None, help="Log file path")
def server_start(foreground, log_level, log_file):
    """Start the guru server."""
    try:
        guru_root = find_guru_root(Path.cwd())
    except GuruNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    if foreground:
        _run_foreground(guru_root, log_level=log_level, log_file=log_file)
    else:
        ensure_server(guru_root, log_level=log_level)
        click.echo("Server is running.")


def _run_foreground(guru_root: Path, log_level: str | None = None, log_file: str | None = None):
    """Run the server in the current process (foreground mode)."""
    import os

    os.environ["GURU_PROJECT_ROOT"] = str(guru_root)

    from guru_server.main import main as server_main

    # Build argv for the server's arg parser
    argv = []
    if log_level:
        argv.extend(["--log-level", log_level])
    if log_file:
        argv.extend(["--log-file", log_file])

    # Override sys.argv for argparse in server main
    import sys as _sys
    original_argv = _sys.argv
    _sys.argv = ["guru-server"] + argv
    try:
        server_main()
    finally:
        _sys.argv = original_argv
```

Also update `ensure_server` call signature — it needs to accept `log_level`:

This requires updating `ensure_server()` in autostart.py to accept an optional `log_level` parameter (in addition to the env var fallback). Update the signature:

```python
def ensure_server(guru_root: Path, timeout: float = 5.0, log_level: str | None = None) -> None:
```

And in the command building:

```python
    log_level_resolved = log_level or os.environ.get("GURU_LOG_LEVEL")
    if log_level_resolved:
        cmd.extend(["--log-level", log_level_resolved])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/guru-cli/tests/test_cli_server.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add packages/guru-cli/src/guru_cli/cli.py packages/guru-core/src/guru_core/autostart.py
git commit -m "feat(guru-cli): Add --foreground, --log-level, --log-file to server start"
```

---

### Task 7: Final integration verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all pass

- [ ] **Step 2: Run linter**

Run: `make lint`
Expected: clean

- [ ] **Step 3: Run formatter**

Run: `make fmt`
Expected: no changes (or auto-fixed)

- [ ] **Step 4: Final commit if formatter changed anything**

```bash
git add -u
git commit -m "chore: Format after logging changes"
```
