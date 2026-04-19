## Dev mode

For iterative server development, use `uv run guru-server-dev` (or
`make dev-server` from the repo root). It runs uvicorn with `--reload`
against a pinned TCP port (`GURU_DEV_PORT`, default `8765`), skips
federation registration and the UDS socket, and reuses an already-running
`ollama serve` when present. It is **not** a drop-in replacement for
`guru-server` — MCP and CLI clients that rely on the UDS socket must run
the regular server.
