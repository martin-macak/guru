# guru-web

Browser UI for the Guru knowledge workbench.

## Development

Install frontend dependencies:

```bash
npm install
```

Run the Vite development server:

```bash
VITE_GURU_API_BASE_URL=http://127.0.0.1:<guru-web-port> npm run dev
```

Use `VITE_GURU_API_BASE_URL` when the web app is running outside `guru-server`. In the
embedded production/runtime path, the browser app is served by `guru-server` and uses the
same origin automatically.

## Test

```bash
npm test
```

## Build

```bash
npm run build
```

This writes static assets to `packages/guru-web/dist/`. When those assets are present,
`guru-server` serves them from its ephemeral localhost web listener.

## Preview

```bash
npm run preview
```
