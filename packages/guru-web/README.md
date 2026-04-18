# guru-web

Browser UI for the Guru knowledge workbench.

## Development

The supported dev setup is:

1. build the frontend once so `guru-server` has a localhost web listener to proxy against
2. start `guru-server`
3. read the current `web.url` from server status
4. point Vite at that runtime URL with `VITE_GURU_API_BASE_URL`

There is no separate stable API port for the browser app. The server publishes an ephemeral
localhost web URL when web assets are available.

Install frontend dependencies:

```bash
npm install
```

Build the frontend and sync packaged runtime assets into `guru-server`:

```bash
npm run build
```

Start the server from the repo root:

```bash
cd /Users/martinmacak/.codex/worktrees/d453/guru
uv run guru server start --foreground
```

In another terminal, inspect the current web runtime URL:

```bash
cd /Users/martinmacak/.codex/worktrees/d453/guru
uv run guru server status
```

Use the reported `web.url` value as the API base for Vite:

```bash
VITE_GURU_API_BASE_URL=http://127.0.0.1:<ephemeral-web-url-port> npm run dev
```

In the embedded runtime path, the browser app is served by `guru-server` and uses the same
origin automatically, so `VITE_GURU_API_BASE_URL` is not needed there.

## Test

```bash
npm test
```

## Build

```bash
npm run build
```

This writes static assets to `packages/guru-web/dist/`. When those assets are present,
the build also syncs them into `packages/guru-server/src/guru_server/web_assets/` so the
installed `guru-server` package can serve the bundled browser app by default.

## Preview

```bash
npm run preview
```
