# Server Logging Design

## Problem

The guru server has no structured logging. Errors are silently swallowed, `server.log`
is truncated on every restart, and there's no way to diagnose issues like the index
timeout (#14). Running `guru server start` gives no visibility into what the server
is doing.

## Design

### Logging Module — `guru_core.logging`

A new module in guru-core providing a `setup_logging()` function that configures
Python's standard `logging` for all guru packages.

```python
def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 3,
) -> None
```

**Format:** `2026-04-10 14:23:01 [INFO] guru_server.api.index: Indexed 42 chunks`

**Handlers:**
- stderr always (via `StreamHandler`)
- Optional `RotatingFileHandler` when `log_file` is provided (10MB, keep 3 backups)

**Level resolution chain:** `INFO` (default) < `GURU_LOG_LEVEL` env var < `--log-level` CLI flag.

This module lives in guru-core because all packages depend on it. Called once at
process startup.

### Server Startup Modes

`guru server start` gains three new flags:

| Flag | Description |
|------|-------------|
| `--foreground` | Run in current process, logs to stderr, Ctrl-C to stop |
| `--log-file PATH` | Tee logs to file in addition to stderr |
| `--log-level LEVEL` | Override `GURU_LOG_LEVEL` env var for this run |

**Daemon mode** (default):
- Autostart passes `--log-file .guru/server.log` and `--log-level` to the
  `guru-server` subprocess via command-line args
- The server process sets up `RotatingFileHandler` internally (10MB, keep 3)
- Autostart no longer redirects stderr — the server owns its own logging
- Logs survive restarts (append) and rotate automatically

**Foreground mode** (`--foreground`):
- Runs the server in the current process (no `subprocess.Popen`)
- Logs visible in terminal via stderr
- `--log-file` optionally tees to file

This shifts log ownership from autostart to the server process itself.

### `guru-server` CLI Arguments

The `guru-server` entry point (in `main.py`) accepts:

| Argument | Default | Description |
|----------|---------|-------------|
| `--log-level` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `--log-file` | None | Path to log file (enables RotatingFileHandler) |

These are parsed in `main()` before calling `setup_logging()` and `uvicorn.run()`.
The `GURU_LOG_LEVEL` env var is checked as fallback when `--log-level` is not passed.

### Logging Throughout the Server

Each module uses `logger = logging.getLogger(__name__)`.

**guru-server modules:**

| Module | Level | What |
|--------|-------|------|
| `api/index.py` | INFO | Indexing started (file count), completed (chunk/doc count, duration) |
| `api/index.py` | ERROR | Embedding or storage failures |
| `embedding.py` | DEBUG | Each embedding call (text length, timing) |
| `embedding.py` | ERROR | Ollama failures |
| `storage.py` | WARNING | JSON parse failures (currently silent) |
| `storage.py` | ERROR | Table access failures (currently returns empty silently) |
| `startup.py` | INFO | Ollama status, model availability |
| `main.py` | INFO | Server starting, socket path, shutdown |

**guru-core:**

| Module | Level | What |
|--------|-------|------|
| `client.py` | DEBUG | HTTP method, path, response status |

**Out of scope:** guru-mcp, guru-cli (thin clients, add later).

### Uvicorn Log Integration

Uvicorn's loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`) are configured to
use the same format and handlers via `log_config` parameter in `uvicorn.run()`.

- Access logs at INFO level
- Uvicorn error logs at ERROR level
- Same plain-text format as application logs

### Autostart Changes

`ensure_server()` in `guru_core/autostart.py`:

- No longer opens `server.log` or redirects stderr
- Passes `--log-file <guru_root>/.guru/server.log` and `--log-level` to the
  `guru-server` subprocess command
- Reads `GURU_LOG_LEVEL` env var and forwards it as `--log-level` arg
- `_read_log_tail()` still works for startup error messages (file now managed by server)
- The subprocess uses `stdout=subprocess.DEVNULL, stderr=log_file` where `log_file`
  is `.guru/server.log` opened in **append mode** (`"a"`, not `"w"`). This catches
  early crashes (before `setup_logging()` runs) and preserves logs across restarts.
- Once `setup_logging()` runs inside the server, the `RotatingFileHandler` takes
  over writing to the same file. The stderr fd becomes a passive safety net for
  unexpected crashes only.

### Storage Error Handling Fix

`storage.py` currently swallows errors silently:
- `_parse_json_list()` catches `json.JSONDecodeError` and returns `[]`
- `_parse_json_dict()` catches `json.JSONDecodeError` and returns `{}`
- `_get_table()` catches `FileNotFoundError` and general exceptions, returns `None`

Fix: add `logger.warning()` / `logger.error()` calls before returning fallback values.
The fallback behavior stays (don't crash the server on bad data), but errors become
visible in logs.

### Trade-off: Dual File Descriptors in Daemon Mode

In daemon mode, `.guru/server.log` is opened twice: once by autostart (stderr redirect,
append mode) and once by the server's `RotatingFileHandler`. After `setup_logging()` runs,
all application logs go through the `RotatingFileHandler`. The stderr fd becomes idle — it
only captures output from unexpected Python-level crashes (segfaults, unhandled C extension
errors). When the `RotatingFileHandler` rotates the file, the stderr fd still points to
the old file (now `server.log.1`). This is acceptable: the only scenario where this matters
is a crash after rotation, which is rare and the output would still be in `server.log.1`.

## Files Changed

| File | Change |
|------|--------|
| `packages/guru-core/src/guru_core/log.py` | New — `setup_logging()` function |
| `packages/guru-core/src/guru_core/autostart.py` | Stop stderr redirect, pass CLI args |
| `packages/guru-core/src/guru_core/client.py` | Add DEBUG logging for HTTP calls |
| `packages/guru-server/src/guru_server/main.py` | Parse args, call `setup_logging()`, configure uvicorn |
| `packages/guru-server/src/guru_server/api/index.py` | Add INFO/ERROR logging |
| `packages/guru-server/src/guru_server/embedding.py` | Add DEBUG/ERROR logging |
| `packages/guru-server/src/guru_server/storage.py` | Add WARNING/ERROR logging |
| `packages/guru-server/src/guru_server/startup.py` | Add INFO logging |
| `packages/guru-cli/src/guru_cli/cli.py` | Add `--foreground`, `--log-file`, `--log-level` flags |
| Tests | New tests for `setup_logging()`, updated autostart tests |
