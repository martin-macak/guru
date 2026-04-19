# Dev Mode for guru-server and guru-web Design

## Problem

Iterating on guru-server or guru-web today is slow. The server has no
`--reload` wiring: every Python change means `Ctrl-C` + `uv run guru-server`,
which re-runs Ollama preflight, federation registration, and UDS/TCP socket
binding. The web is worse — to see a code change reflected where the server
actually serves the UI (`packages/guru-server/src/guru_server/web_assets`),
you must `npm run build` (typecheck + `vite build` + sync), a multi-second
cycle that discourages small experiments. `npm run dev` exists but has no
path to the backend, so nothing with live data is reachable.

There is no Make target for either workflow.

## Goals

- Edit Python in guru-server/guru-core/guru-graph and see the HTTP API
  pick up the change without restart.
- Edit React/TS in guru-web and see the browser update via Vite HMR, with
  the web still able to call the live backend.
- Start each side independently (`make dev-server`, `make dev-web`) or both
  together (`make dev`) with a clean Ctrl-C.

## Non-goals

- MCP/CLI parity in dev. Those clients use the UDS socket; the dev server is
  TCP-only. If a contributor needs MCP-over-UDS live, they run the regular
  `guru-server` in another terminal.
- Federation visibility. Dev server does not register with `guru list`.
- Parallel dev and prod server on the same `.guru/` — stick to one at a time.
- Dev server as a production deployment target.

## Design

### Server dev entry point — `guru-server-dev`

A new console script in guru-server that runs a stripped-down supervisor and
delegates HTTP lifecycle to `uvicorn`'s reloader.

**New module:** `packages/guru-server/src/guru_server/dev.py`

**Console script:** `guru-server-dev = "guru_server.dev:main"`, added to
`packages/guru-server/pyproject.toml` alongside the existing `guru-server`.

**Parent-process responsibilities** (run once, survive reloads):

1. `setup_logging(...)` from `guru_core.log` (same as prod).
2. Read `GURU_PROJECT_ROOT` (default: cwd). Fail fast with a clear message
   if `.guru/` is missing — same contract as prod.
3. `check_ollama_installed()`.
4. If `ollama serve` is already listening, reuse it; otherwise
   `start_ollama_serve()` and remember we own it so we can stop it on exit.
5. `check_model_available("nomic-embed-text")`.
6. Resolve the bind port: `int(os.environ.get("GURU_DEV_PORT", "8765"))`.
7. Call `uvicorn.run("guru_server.dev:create_dev_app", factory=True,
   host="127.0.0.1", port=<port>, reload=True, reload_dirs=[...],
   log_config=_uvicorn_log_config())`.
8. On exit, stop Ollama only if we started it.

**Worker-process responsibilities** (`create_dev_app()` factory, runs on
every reload):

1. Read `GURU_PROJECT_ROOT` again (fresh process, fresh env).
2. `config = resolve_config(project_root=...)`.
3. Build `VectorStore(db_path=".guru/db")`, `OllamaEmbedder()`, and
   `EmbeddingCache(db_path=_resolve_cache_db_path())` — the same construction
   `main.py` does today.
4. `app = create_app(store=..., embedder=..., config=..., project_root=...,
   embed_cache=...)`.
5. Return `app`. No federation registration. No UDS listener. No
   `bind_web_listener_sockets` call — uvicorn binds TCP itself via the
   `port=` arg.

**Reload scope** — `reload_dirs` lists the three source trees that can feed
code into the server:

- `packages/guru-server/src`
- `packages/guru-core/src`
- `packages/guru-graph/src`

Resolved to absolute paths by walking up from `Path(__file__)` to the repo
root (the first ancestor containing a `packages/` directory). Absolute
paths are passed to `uvicorn.run(..., reload_dirs=[...])` so the reloader
behaves identically regardless of the user's cwd.

`reload_excludes` defaults are sufficient (`__pycache__`, `.pyc`, tests
aren't in `reload_dirs` anyway).

**What the dev server deliberately omits versus prod `main.py`:**

| Behavior | Prod `main.py` | Dev |
|---|---|---|
| Ollama preflight + spawn | every start | once per supervisor; reuses existing |
| Federation registration | yes | no |
| UDS socket bind | yes | no |
| TCP socket | only if web enabled + available | always, pinned port |
| PID file | yes | no |
| Web asset resolution | yes, from `web_assets` | resolved but not used — the browser is on Vite, never on the dev server's static mount |

Note that `/web/boot` is still served by the dev server. The web client in
dev mode reads `VITE_GURU_API_BASE_URL=""` (unset), so `/web/boot` goes
through the Vite proxy → dev server, returning a real boot payload. The
`web.url` field in that payload points to the server's TCP port — the
browser ignores it (it's already on the Vite origin) but other consumers
see a coherent value. Whether `web_assets/` contains a stale or empty
bundle is irrelevant in dev because the browser never requests `/` from
the dev server.

### Web dev with Vite proxy

Extend `packages/guru-web/vite.config.ts` with a `server.proxy` block. The
target port is read from the environment so it stays in sync with whatever
`GURU_DEV_PORT` the user set.

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const DEV_PORT = Number.parseInt(process.env.GURU_DEV_PORT ?? "8765", 10);

const SERVER_PREFIXES = [
  "/web",
  "/graph",
  "/documents",
  "/search",
  "/status",
  "/jobs",
  "/index",
  "/cache",
  "/sync",
];

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: Object.fromEntries(
      SERVER_PREFIXES.map((p) => [
        p,
        { target: `http://127.0.0.1:${DEV_PORT}`, changeOrigin: true },
      ]),
    ),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
```

The prefix list mirrors the top-level API router prefixes used today
(`api/__init__.py` + `web.py`). It must be extended when a new top-level
prefix is added to the server — a comment in `vite.config.ts` states this
obligation.

`VITE_GURU_API_BASE_URL` is left **unset** in dev. That makes
`resolveApiUrl(path)` (in `packages/guru-web/src/lib/api/client.ts`) return
the relative path, which Vite's proxy then forwards. No client-side code
changes.

When `guru-web` is built for prod (`npm run build` + sync to
`guru_server/web_assets`), the server serves the bundle itself, same origin,
unchanged behavior.

### Makefile targets

Add a new "Development" section to the Makefile with three targets.

```make
# ─── Development ─────────────────────────────────────────────────────────────

GURU_DEV_PORT ?= 8765

.PHONY: dev-server
dev-server:
	GURU_DEV_PORT=$(GURU_DEV_PORT) uv run guru-server-dev

.PHONY: dev-web
dev-web:
	cd packages/guru-web && GURU_DEV_PORT=$(GURU_DEV_PORT) npm run dev

.PHONY: dev
dev:
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-server & \
	$(MAKE) dev-web & \
	wait
```

`make help` gains a Development section listing all three targets and noting
that `GURU_DEV_PORT` is overridable.

Rationale for the `dev` target shape:

- `trap 'kill 0' EXIT INT TERM` ensures Ctrl-C kills both child
  processes (and their grandchildren) by targeting process group `0`.
- `&` + `wait` runs both in parallel and blocks until either exits. If the
  server crashes, the trap fires, kills the web, and `make` exits non-zero.
- Zero new dependencies (no `concurrently`, `honcho`, `foreman`).

### Error paths

| Scenario | Behavior |
|---|---|
| `.guru/` missing | supervisor logs error and exits 1 (same as prod) |
| Ollama not installed | supervisor logs error and exits 1 (same as prod) |
| Port 8765 already bound | uvicorn raises; supervisor logs and exits 1. User either sets `GURU_DEV_PORT=...` or stops the other process |
| Syntax error in reloaded file | uvicorn logs traceback, keeps running; next save triggers another reload |
| Vite proxy gets a connection refused | browser sees 502/ECONNREFUSED from dev server; expected if `dev-server` isn't running yet |

## Testing

The dev entry point is intentionally thin. Unit coverage focuses on the
pieces that aren't exercised by an already-running prod server:

- `guru_server.dev.create_dev_app` — returns a FastAPI app with the routers
  mounted and no federation state. Reuses existing app-factory tests as a
  template.
- `guru_server.dev.main` — smoke test that it parses `GURU_DEV_PORT`, fails
  fast on missing `.guru/`, and passes expected args to
  `uvicorn.run` (mock uvicorn). No end-to-end HTTP test — uvicorn reload is
  its own library's concern.

No BDD feature is added. Dev mode is a contributor workflow, not a user
acceptance surface.

## Documentation

- `AGENTS.md` "Commands" section: add `make dev-server`, `make dev-web`,
  `make dev`.
- `packages/guru-web/README.md`: note that `npm run dev` now proxies to
  `127.0.0.1:$GURU_DEV_PORT` and the server side is expected to be running
  via `make dev-server`.
- `packages/guru-server/README.md`: note `guru-server-dev` and its
  trade-offs versus `guru-server`.
