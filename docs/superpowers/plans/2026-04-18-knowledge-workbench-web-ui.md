# Knowledge Workbench Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a browser-based Knowledge Workbench served by `guru-server`, with parity to the current TUI's read/query/operate capabilities plus a React Flow graph view, while preserving Guru's server-centric architecture.

**Architecture:** Add a new `packages/guru-web` frontend package for React/Vite development and production build output, then extend `guru-server` to own the runtime web surface: config, ephemeral localhost port allocation, static asset serving, boot metadata, and explicit browser opening. Reuse existing REST surfaces where possible, add only the browser-specific boot/runtime endpoints that are missing, and keep all browser-to-backend traffic flowing through `guru-server`.

**Tech Stack:** Python 3.13 · FastAPI · click · React · TypeScript · Vite · shadcn/ui · React Router · TanStack Query · React Flow · Vitest · React Testing Library · jsdom

---

## Scope guard

This plan assumes the approved spec at `docs/superpowers/specs/2026-04-18-knowledge-workbench-web-ui-design.md`.

This is one cohesive subsystem, but it has two clearly separable runtime halves:

- backend/runtime web hosting in `guru-server`
- browser client in `packages/guru-web`

They are developed in parallel-friendly slices, but the browser must never bypass the server surface.

---

## File structure

**New frontend package**

- `packages/guru-web/package.json` — frontend scripts and dependency declarations
- `packages/guru-web/tsconfig.json` — TypeScript compiler config
- `packages/guru-web/tsconfig.node.json` — Vite/node TS config
- `packages/guru-web/vite.config.ts` — Vite build/dev/test configuration
- `packages/guru-web/index.html` — Vite HTML entry
- `packages/guru-web/src/main.tsx` — React bootstrap
- `packages/guru-web/src/app/App.tsx` — top-level shell and routing host
- `packages/guru-web/src/app/router.tsx` — browser routes and deep-link model
- `packages/guru-web/src/app/providers.tsx` — QueryClient/provider composition
- `packages/guru-web/src/app/layout/AppShell.tsx` — browser-first workbench layout
- `packages/guru-web/src/components/ui/*` — shadcn/ui generated primitives
- `packages/guru-web/src/lib/api/client.ts` — typed HTTP client for browser requests
- `packages/guru-web/src/lib/api/types.ts` — browser-local API response/input types when useful
- `packages/guru-web/src/lib/api/hooks.ts` — TanStack Query wrappers
- `packages/guru-web/src/lib/state/workbench.ts` — shared browser UI state
- `packages/guru-web/src/lib/state/url.ts` — URL <-> state sync helpers
- `packages/guru-web/src/features/investigate/*` — investigate surface
- `packages/guru-web/src/features/graph/*` — React Flow graph surface
- `packages/guru-web/src/features/query/*` — read-only query surface
- `packages/guru-web/src/features/operate/*` — operate surface
- `packages/guru-web/src/features/knowledge-tree/*` — shared knowledge tree
- `packages/guru-web/src/features/inspector/*` — right-side detail inspector
- `packages/guru-web/src/test/setup.ts` — jsdom/test bootstrap
- `packages/guru-web/src/test/render.tsx` — shared render helper
- `packages/guru-web/src/**/*.test.ts(x)` — unit/integration/react tests

**Server/runtime web support**

- `packages/guru-server/src/guru_server/config.py` — add typed web config fields
- `packages/guru-server/src/guru_server/app.py` — mount runtime web API/static routes and hold web runtime state
- `packages/guru-server/src/guru_server/main.py` — initialize web runtime on process start
- `packages/guru-server/src/guru_server/startup.py` — web startup helpers if existing startup utilities fit better here
- `packages/guru-server/src/guru_server/api/models.py` — browser boot/runtime response models
- `packages/guru-server/src/guru_server/api/status.py` — include web runtime status in status responses
- `packages/guru-server/src/guru_server/api/web.py` — new browser boot/runtime routes
- `packages/guru-server/src/guru_server/web_runtime.py` — ephemeral port allocation, asset detection, browser-open helpers
- `packages/guru-server/tests/test_web_runtime.py` — runtime web lifecycle tests
- `packages/guru-server/tests/test_web_api.py` — browser boot/status/open API tests
- `packages/guru-server/tests/test_status_api.py` — web status coverage

**CLI integration**

- `packages/guru-cli/src/guru_cli/cli.py` — `guru server web-open`
- `packages/guru-cli/tests/test_cli_server.py` — CLI coverage for `web-open`

**Workspace/build integration**

- `pyproject.toml` — workspace/package registration if needed
- `package.json` or repo-root frontend helper scripts if the repo already uses them
- `.gitignore` — frontend build artifacts if not already ignored

This split keeps responsibilities clean: frontend package owns browser behavior, server owns runtime hosting and browser-facing API, CLI owns human entrypoints.

---

## Task 1: Scaffold the frontend package and test stack

**Files:**
- Create: `packages/guru-web/package.json`
- Create: `packages/guru-web/tsconfig.json`
- Create: `packages/guru-web/tsconfig.node.json`
- Create: `packages/guru-web/vite.config.ts`
- Create: `packages/guru-web/index.html`
- Create: `packages/guru-web/src/main.tsx`
- Create: `packages/guru-web/src/index.css`
- Create: `packages/guru-web/src/app/App.tsx`
- Create: `packages/guru-web/src/lib/utils.ts`
- Create: `packages/guru-web/src/components/ui/button.tsx`
- Create: `packages/guru-web/src/test/setup.ts`
- Create: `packages/guru-web/src/test/render.tsx`
- Create: `packages/guru-web/src/app/App.test.tsx`

- [ ] **Step 1: Write the failing frontend smoke test**

Create `packages/guru-web/src/app/App.test.tsx`:

```tsx
import { render, screen } from "../test/render";
import { App } from "./App";

test("renders guru web shell title", () => {
  render(<App />);
  expect(screen.getByText("Guru")).toBeInTheDocument();
  expect(screen.getByText("Knowledge Workbench")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify the package is not wired yet**

Run:

```bash
cd packages/guru-web && npm test -- --runInBand
```

Expected: FAIL because the package and test runner do not exist yet.

- [ ] **Step 3: Add the minimal package/tooling files**

Create `packages/guru-web/package.json`:

```json
{
  "name": "guru-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "@radix-ui/react-slot": "^1.1.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^0.453.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "reactflow": "^11.11.4",
    "tailwind-merge": "^2.5.4"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "jsdom": "^25.0.1",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.14",
    "typescript": "^5.6.3",
    "vite": "^5.4.10",
    "vitest": "^2.1.4"
  }
}
```

Create `packages/guru-web/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
```

Create `packages/guru-web/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Create `packages/guru-web/src/lib/utils.ts`:

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

Create `packages/guru-web/src/components/ui/button.tsx`:

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-slate-900 text-white hover:bg-slate-800",
        outline: "border border-slate-300 bg-white hover:bg-slate-50",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant }), className)} ref={ref} {...props} />;
  },
);

Button.displayName = "Button";
```

Create `packages/guru-web/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  font-family: ui-sans-serif, system-ui, sans-serif;
  background: #f8fafc;
  color: #0f172a;
}
```

Create `packages/guru-web/src/test/render.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";

export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

export * from "@testing-library/react";
export { renderWithProviders as render };
```

Create `packages/guru-web/src/app/App.tsx`:

```tsx
export function App() {
  return (
    <main>
      <h1>Guru</h1>
      <p>Knowledge Workbench</p>
    </main>
  );
}
```

Create `packages/guru-web/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./app/App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 4: Run the smoke test to verify the scaffold works**

Run:

```bash
cd packages/guru-web && npm test
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Verify the dev and build entrypoints**

Run:

```bash
cd packages/guru-web && npm run build
```

Expected: PASS and emit `dist/`.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web
git commit -m "feat: scaffold guru web package"
```

---

## Task 2: Add server web runtime config, status, and asset serving

**Files:**
- Modify: `packages/guru-server/src/guru_server/config.py`
- Modify: `packages/guru-server/src/guru_server/app.py`
- Modify: `packages/guru-server/src/guru_server/main.py`
- Modify: `packages/guru-server/src/guru_server/api/status.py`
- Modify: `packages/guru-server/src/guru_server/api/models.py`
- Create: `packages/guru-server/src/guru_server/api/web.py`
- Create: `packages/guru-server/src/guru_server/web_runtime.py`
- Create: `packages/guru-server/tests/test_web_runtime.py`
- Create: `packages/guru-server/tests/test_web_api.py`

- [ ] **Step 1: Write failing server tests for web runtime degradation**

Create `packages/guru-server/tests/test_web_runtime.py`:

```python
from pathlib import Path

from guru_server.web_runtime import build_web_runtime


def test_missing_assets_yields_unavailable_runtime(tmp_path: Path):
    runtime = build_web_runtime(
        project_root=tmp_path,
        assets_dir=tmp_path / "missing-dist",
        enabled=True,
    )
    assert runtime.enabled is True
    assert runtime.available is False
    assert runtime.url is None
    assert runtime.reason == "assets_missing"
```

Create `packages/guru-server/tests/test_web_api.py`:

```python
from fastapi.testclient import TestClient

from guru_server.app import create_app


def test_web_boot_reports_unavailable_runtime(mock_store, mock_embedder, embed_cache):
    app = create_app(
        store=mock_store,
        embedder=mock_embedder,
        embed_cache=embed_cache,
        auto_index=False,
    )
    app.state.web_runtime = type(
        "WebRuntime",
        (),
        {
            "enabled": True,
            "available": False,
            "url": None,
            "reason": "assets_missing",
            "auto_open": False,
        },
    )()
    with TestClient(app) as client:
        response = client.get("/web/boot")
    assert response.status_code == 200
    assert response.json()["web"]["available"] is False
    assert response.json()["web"]["reason"] == "assets_missing"
```

- [ ] **Step 2: Run the tests to verify the runtime surface does not exist**

Run:

```bash
uv run pytest packages/guru-server/tests/test_web_runtime.py packages/guru-server/tests/test_web_api.py -q
```

Expected: FAIL because `guru_server.web_runtime` and `/web/boot` do not exist yet.

- [ ] **Step 3: Add typed web runtime config and state**

Update `packages/guru-server/src/guru_server/config.py` to add:

```python
from pydantic import BaseModel


class WebConfig(BaseModel):
    enabled: bool = True
    auto_open: bool = False
```

and include it in the top-level Guru config model:

```python
web: WebConfig = Field(default_factory=WebConfig)
```

Create `packages/guru-server/src/guru_server/web_runtime.py`:

```python
from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebRuntime:
    enabled: bool
    available: bool
    url: str | None
    port: int | None
    assets_dir: Path | None
    reason: str | None
    auto_open: bool


def _pick_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def build_web_runtime(*, project_root: Path, assets_dir: Path, enabled: bool, auto_open: bool = False) -> WebRuntime:
    if not enabled:
        return WebRuntime(False, False, None, None, None, "disabled", auto_open)
    if not assets_dir.exists():
        return WebRuntime(True, False, None, None, None, "assets_missing", auto_open)
    port = _pick_free_port()
    return WebRuntime(True, True, f"http://127.0.0.1:{port}", port, assets_dir, None, auto_open)
```

- [ ] **Step 4: Mount web boot/status routes and expose runtime state**

Create `packages/guru-server/src/guru_server/api/web.py`:

```python
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/web/boot")
def web_boot(request: Request) -> dict:
    runtime = request.app.state.web_runtime
    return {
        "project": {
            "name": request.app.state.project_name,
            "root": str(request.app.state.project_root),
        },
        "web": {
            "enabled": runtime.enabled,
            "available": runtime.available,
            "url": runtime.url,
            "reason": runtime.reason,
            "autoOpen": runtime.auto_open,
        },
        "graph": {
            "enabled": bool(request.app.state.graph_enabled),
        },
    }
```

Update `packages/guru-server/src/guru_server/app.py` to initialize `app.state.web_runtime` and include the router:

```python
from guru_server.api.web import router as web_router
from guru_server.web_runtime import build_web_runtime

app.state.web_runtime = build_web_runtime(
    project_root=Path(app.state.project_root),
    assets_dir=Path(app.state.project_root) / "packages" / "guru-web" / "dist",
    enabled=bool(app.state.config.web.enabled),
    auto_open=bool(app.state.config.web.auto_open),
)

app.include_router(web_router)
```

Update `packages/guru-server/src/guru_server/api/status.py` to include:

```python
"web": {
    "enabled": request.app.state.web_runtime.enabled,
    "available": request.app.state.web_runtime.available,
    "url": request.app.state.web_runtime.url,
    "reason": request.app.state.web_runtime.reason,
},
```

- [ ] **Step 5: Run the targeted tests**

Run:

```bash
uv run pytest packages/guru-server/tests/test_web_runtime.py packages/guru-server/tests/test_web_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Add static asset serving**

Update `packages/guru-server/src/guru_server/app.py` to mount static files when the runtime is available:

```python
from fastapi.staticfiles import StaticFiles

if app.state.web_runtime.available and app.state.web_runtime.assets_dir is not None:
    app.mount("/", StaticFiles(directory=app.state.web_runtime.assets_dir, html=True), name="web")
```

This must happen after API routes are included so `/api/...`, `/status`, `/web/boot`, and existing server routes are not shadowed.

- [ ] **Step 7: Run focused status tests**

Run:

```bash
uv run pytest packages/guru-server/tests/test_web_runtime.py packages/guru-server/tests/test_web_api.py packages/guru-server/tests/test_status_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add packages/guru-server/src/guru_server/config.py \
        packages/guru-server/src/guru_server/app.py \
        packages/guru-server/src/guru_server/api/status.py \
        packages/guru-server/src/guru_server/api/models.py \
        packages/guru-server/src/guru_server/api/web.py \
        packages/guru-server/src/guru_server/web_runtime.py \
        packages/guru-server/tests/test_web_runtime.py \
        packages/guru-server/tests/test_web_api.py
git commit -m "feat: add guru server web runtime"
```

---

## Task 3: Add explicit browser-opening support and CLI integration

**Files:**
- Modify: `packages/guru-server/src/guru_server/web_runtime.py`
- Modify: `packages/guru-server/src/guru_server/api/web.py`
- Modify: `packages/guru-cli/src/guru_cli/cli.py`
- Modify: `packages/guru-cli/tests/test_cli_server.py`
- Create: `packages/guru-server/tests/test_web_open.py`

- [ ] **Step 1: Write failing tests for `web-open`**

Append to `packages/guru-server/tests/test_web_open.py`:

```python
from unittest.mock import patch

from guru_server.web_runtime import open_web_browser


def test_open_web_browser_returns_false_without_url():
    assert open_web_browser(None) is False


def test_open_web_browser_opens_when_url_present():
    with patch("webbrowser.open", return_value=True) as mock_open:
        assert open_web_browser("http://127.0.0.1:41773") is True
    mock_open.assert_called_once_with("http://127.0.0.1:41773")
```

Append to `packages/guru-cli/tests/test_cli_server.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


def test_server_web_open_invokes_backend_url(runner):
    fake_client = MagicMock()
    fake_client.web_open = AsyncMock(return_value={"opened": True, "url": "http://127.0.0.1:41773"})
    with patch("guru_cli.cli._get_client", return_value=fake_client):
        result = runner.invoke(cli, ["server", "web-open"])
    assert result.exit_code == 0
    assert "41773" in result.output
```

- [ ] **Step 2: Run the tests to verify the command is missing**

Run:

```bash
uv run pytest packages/guru-server/tests/test_web_open.py packages/guru-cli/tests/test_cli_server.py -q
```

Expected: FAIL because `open_web_browser` and `server web-open` do not exist yet.

- [ ] **Step 3: Implement browser opening helpers and API**

Update `packages/guru-server/src/guru_server/web_runtime.py`:

```python
import webbrowser


def open_web_browser(url: str | None) -> bool:
    if not url:
        return False
    return bool(webbrowser.open(url))
```

Append to `packages/guru-server/src/guru_server/api/web.py`:

```python
from guru_server.web_runtime import open_web_browser


@router.post("/web/open")
def web_open(request: Request) -> dict:
    runtime = request.app.state.web_runtime
    opened = open_web_browser(runtime.url)
    return {"opened": opened, "url": runtime.url}
```

- [ ] **Step 4: Add the CLI command**

Append to the `server` group in `packages/guru-cli/src/guru_cli/cli.py`:

```python
@server.command("web-open")
def server_web_open():
    """Open the Guru web UI in a browser."""
    client = _get_client()
    result = _run(client.web_open())
    if result["url"] is None:
        click.echo("Web UI unavailable.")
        raise SystemExit(1)
    click.echo(f"Opened {result['url']}" if result["opened"] else f"Web UI: {result['url']}")
```

If `GuruClient` lacks `web_open`, add it in `packages/guru-core/src/guru_core/client.py` as:

```python
async def web_open(self) -> dict:
    resp = await self._request("POST", "/web/open")
    return resp.json()
```

- [ ] **Step 5: Run the focused tests**

Run:

```bash
uv run pytest packages/guru-server/tests/test_web_open.py packages/guru-cli/tests/test_cli_server.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-server/src/guru_server/web_runtime.py \
        packages/guru-server/src/guru_server/api/web.py \
        packages/guru-core/src/guru_core/client.py \
        packages/guru-cli/src/guru_cli/cli.py \
        packages/guru-cli/tests/test_cli_server.py \
        packages/guru-server/tests/test_web_open.py
git commit -m "feat: add guru server web open command"
```

---

## Task 4: Build the browser app shell, routing, and boot handshake

**Files:**
- Create: `packages/guru-web/src/app/router.tsx`
- Create: `packages/guru-web/src/app/providers.tsx`
- Create: `packages/guru-web/src/app/layout/AppShell.tsx`
- Create: `packages/guru-web/src/lib/api/client.ts`
- Create: `packages/guru-web/src/lib/api/hooks.ts`
- Create: `packages/guru-web/src/lib/state/workbench.ts`
- Create: `packages/guru-web/src/lib/state/url.ts`
- Modify: `packages/guru-web/src/app/App.tsx`
- Create: `packages/guru-web/src/app/AppShell.test.tsx`

- [ ] **Step 1: Write failing tests for boot loading and shell routing**

Create `packages/guru-web/src/app/AppShell.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { render, screen } from "../test/render";
import { App } from "./App";

const server = setupServer(
  http.get("/web/boot", () =>
    HttpResponse.json({
      project: { name: "guru", root: "/tmp/guru" },
      web: { enabled: true, available: true, url: "http://127.0.0.1:41773", reason: null, autoOpen: false },
      graph: { enabled: true },
    }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("renders investigate as default shell surface", async () => {
  render(<App />);
  expect(await screen.findByText("Investigate")).toBeInTheDocument();
  expect(screen.getByText("guru")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify the boot handshake is missing**

Run:

```bash
cd packages/guru-web && npm test -- AppShell.test.tsx
```

Expected: FAIL because boot API hooks and app shell do not exist.

- [ ] **Step 3: Add typed boot client and providers**

Create `packages/guru-web/src/lib/api/client.ts`:

```ts
export type BootPayload = {
  project: { name: string; root: string };
  web: { enabled: boolean; available: boolean; url: string | null; reason: string | null; autoOpen: boolean };
  graph: { enabled: boolean };
};

export async function getBoot(): Promise<BootPayload> {
  const response = await fetch("/web/boot");
  if (!response.ok) throw new Error(`boot failed: ${response.status}`);
  return response.json() as Promise<BootPayload>;
}
```

Create `packages/guru-web/src/lib/api/hooks.ts`:

```ts
import { useQuery } from "@tanstack/react-query";

import { getBoot } from "./client";

export function useBootQuery() {
  return useQuery({ queryKey: ["boot"], queryFn: getBoot });
}
```

Create `packages/guru-web/src/app/providers.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

export function AppProviders({ children }: PropsWithChildren) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
```

- [ ] **Step 4: Add shell layout and default route**

Create `packages/guru-web/src/app/layout/AppShell.tsx`:

```tsx
type AppShellProps = { projectName: string };

export function AppShell({ projectName }: AppShellProps) {
  return (
    <div>
      <header>
        <h1>{projectName}</h1>
        <nav>
          <button>Investigate</button>
          <button>Graph</button>
          <button>Query</button>
          <button>Operate</button>
        </nav>
      </header>
      <main>
        <h2>Investigate</h2>
      </main>
    </div>
  );
}
```

Update `packages/guru-web/src/app/App.tsx`:

```tsx
import { AppProviders } from "./providers";
import { useBootQuery } from "../lib/api/hooks";
import { AppShell } from "./layout/AppShell";

function AppBody() {
  const boot = useBootQuery();
  if (boot.isLoading) return <p>Loading Guru…</p>;
  if (boot.isError) return <p>Server unavailable</p>;
  return <AppShell projectName={boot.data.project.name} />;
}

export function App() {
  return (
    <AppProviders>
      <AppBody />
    </AppProviders>
  );
}
```

- [ ] **Step 5: Run the shell test**

Run:

```bash
cd packages/guru-web && npm test -- AppShell.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/guru-web/src/app/App.tsx \
        packages/guru-web/src/app/providers.tsx \
        packages/guru-web/src/app/layout/AppShell.tsx \
        packages/guru-web/src/lib/api/client.ts \
        packages/guru-web/src/lib/api/hooks.ts \
        packages/guru-web/src/app/AppShell.test.tsx
git commit -m "feat: add guru web app shell"
```

---

## Task 5: Implement Investigate, Knowledge Tree, and Inspector

**Files:**
- Create: `packages/guru-web/src/features/investigate/InvestigatePage.tsx`
- Create: `packages/guru-web/src/features/investigate/InvestigatePage.test.tsx`
- Create: `packages/guru-web/src/features/knowledge-tree/KnowledgeTree.tsx`
- Create: `packages/guru-web/src/features/inspector/Inspector.tsx`
- Create: `packages/guru-web/src/lib/state/workbench.ts`
- Modify: `packages/guru-web/src/app/layout/AppShell.tsx`

- [ ] **Step 1: Write failing Investigate test**

Create `packages/guru-web/src/features/investigate/InvestigatePage.test.tsx`:

```tsx
import { render, screen } from "../../test/render";
import { InvestigatePage } from "./InvestigatePage";

test("renders search box and result panels", () => {
  render(<InvestigatePage />);
  expect(screen.getByPlaceholderText("Search knowledge base")).toBeInTheDocument();
  expect(screen.getByText("Results")).toBeInTheDocument();
  expect(screen.getByText("Inspector")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify the page does not exist**

Run:

```bash
cd packages/guru-web && npm test -- InvestigatePage.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Add minimal investigate shell components**

Create `packages/guru-web/src/features/investigate/InvestigatePage.tsx`:

```tsx
export function InvestigatePage() {
  return (
    <section>
      <input placeholder="Search knowledge base" />
      <div>
        <section><h3>Results</h3></section>
        <aside><h3>Inspector</h3></aside>
      </div>
    </section>
  );
}
```

Create `packages/guru-web/src/features/knowledge-tree/KnowledgeTree.tsx`:

```tsx
export function KnowledgeTree() {
  return <aside><h3>Knowledge Tree</h3></aside>;
}
```

Create `packages/guru-web/src/features/inspector/Inspector.tsx`:

```tsx
export function Inspector() {
  return <aside><h3>Inspector</h3></aside>;
}
```

Update `packages/guru-web/src/app/layout/AppShell.tsx` to mount `KnowledgeTree` on the left and `InvestigatePage` as the default center surface.

- [ ] **Step 4: Run the investigate test**

Run:

```bash
cd packages/guru-web && npm test -- InvestigatePage.test.tsx AppShell.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Add URL/shared selection state**

Create `packages/guru-web/src/lib/state/workbench.ts` with:

```ts
export type WorkbenchSelection = {
  documentId: string | null;
  artifactId: string | null;
};
```

Create `packages/guru-web/src/lib/state/url.ts` with:

```ts
export type Surface = "investigate" | "graph" | "query" | "operate";

export function parseSurface(search: URLSearchParams): Surface {
  const value = search.get("surface");
  return value === "graph" || value === "query" || value === "operate"
    ? value
    : "investigate";
}
```

- [ ] **Step 6: Run the frontend suite for the new surface**

Run:

```bash
cd packages/guru-web && npm test
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/guru-web/src/features/investigate \
        packages/guru-web/src/features/knowledge-tree \
        packages/guru-web/src/features/inspector \
        packages/guru-web/src/lib/state \
        packages/guru-web/src/app/layout/AppShell.tsx
git commit -m "feat: add investigate shell for guru web"
```

---

## Task 6: Implement Query and Operate browser surfaces

**Files:**
- Create: `packages/guru-web/src/features/query/QueryPage.tsx`
- Create: `packages/guru-web/src/features/query/QueryPage.test.tsx`
- Create: `packages/guru-web/src/features/operate/OperatePage.tsx`
- Create: `packages/guru-web/src/features/operate/OperatePage.test.tsx`
- Modify: `packages/guru-web/src/app/layout/AppShell.tsx`
- Modify: `packages/guru-web/src/lib/api/client.ts`

- [ ] **Step 1: Write failing tests for Query and Operate**

Create `packages/guru-web/src/features/query/QueryPage.test.tsx`:

```tsx
import { render, screen } from "../../test/render";
import { QueryPage } from "./QueryPage";

test("renders read-only query controls", () => {
  render(<QueryPage />);
  expect(screen.getByText("Read-only Query")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Run Query" })).toBeInTheDocument();
});
```

Create `packages/guru-web/src/features/operate/OperatePage.test.tsx`:

```tsx
import { render, screen } from "../../test/render";
import { OperatePage } from "./OperatePage";

test("renders runtime status cards", () => {
  render(<OperatePage />);
  expect(screen.getByText("Server Status")).toBeInTheDocument();
  expect(screen.getByText("Graph Status")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify the pages do not exist**

Run:

```bash
cd packages/guru-web && npm test -- QueryPage.test.tsx OperatePage.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Add minimal pages**

Create `QueryPage.tsx`:

```tsx
export function QueryPage() {
  return (
    <section>
      <h2>Read-only Query</h2>
      <textarea aria-label="Cypher query" />
      <button>Run Query</button>
    </section>
  );
}
```

Create `OperatePage.tsx`:

```tsx
export function OperatePage() {
  return (
    <section>
      <h2>Server Status</h2>
      <h2>Graph Status</h2>
    </section>
  );
}
```

Update `AppShell.tsx` so top-nav selection can switch displayed surface.

- [ ] **Step 4: Run the new page tests**

Run:

```bash
cd packages/guru-web && npm test -- QueryPage.test.tsx OperatePage.test.tsx AppShell.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/src/features/query \
        packages/guru-web/src/features/operate \
        packages/guru-web/src/app/layout/AppShell.tsx
git commit -m "feat: add query and operate web surfaces"
```

---

## Task 7: Implement React Flow graph surface with selection-centered neighborhood

**Files:**
- Create: `packages/guru-web/src/features/graph/GraphPage.tsx`
- Create: `packages/guru-web/src/features/graph/GraphPage.test.tsx`
- Create: `packages/guru-web/src/features/graph/mapGraph.ts`
- Modify: `packages/guru-web/src/lib/api/client.ts`
- Modify: `packages/guru-web/src/app/layout/AppShell.tsx`

- [ ] **Step 1: Write failing graph test**

Create `packages/guru-web/src/features/graph/GraphPage.test.tsx`:

```tsx
import { render, screen } from "../../test/render";
import { GraphPage } from "./GraphPage";

test("renders graph controls and selected node label", () => {
  render(<GraphPage />);
  expect(screen.getByText("Graph")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Fit View" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify graph surface does not exist**

Run:

```bash
cd packages/guru-web && npm test -- GraphPage.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Add React Flow page shell**

Create `GraphPage.tsx`:

```tsx
import ReactFlow, { Background, Controls, MiniMap } from "reactflow";
import "reactflow/dist/style.css";

const nodes = [{ id: "focus", position: { x: 0, y: 0 }, data: { label: "Focused node" } }];

export function GraphPage() {
  return (
    <section>
      <h2>Graph</h2>
      <div style={{ height: 480 }} aria-label="graph-canvas">
        <ReactFlow nodes={nodes} edges={[]} fitView>
          <MiniMap />
          <Controls />
          <Background />
        </ReactFlow>
      </div>
    </section>
  );
}
```

Create `mapGraph.ts`:

```ts
export type GraphNodeVm = { id: string; label: string };
export type GraphEdgeVm = { id: string; source: string; target: string; label?: string };
```

In the full implementation of this task, replace the static `nodes` constant with mapped bounded-neighborhood data fetched from `guru-server`, while keeping React Flow as a renderer rather than the source of truth.

- [ ] **Step 4: Run the graph test**

Run:

```bash
cd packages/guru-web && npm test -- GraphPage.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/src/features/graph \
        packages/guru-web/src/app/layout/AppShell.tsx \
        packages/guru-web/src/lib/api/client.ts
git commit -m "feat: add react flow graph surface"
```

---

## Task 8: Add production build integration and runtime dev/prod documentation

**Files:**
- Modify: `packages/guru-server/src/guru_server/web_runtime.py`
- Modify: `packages/guru-server/src/guru_server/app.py`
- Modify: `packages/guru-web/package.json`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `packages/guru-web/README.md`
- Modify: `docs/superpowers/specs/2026-04-18-knowledge-workbench-web-ui-design.md` only if the implementation clarified a necessary detail

- [ ] **Step 1: Write failing test for serving built assets**

Append to `packages/guru-server/tests/test_web_runtime.py`:

```python
def test_runtime_points_at_built_frontend_assets(tmp_path: Path):
    assets_dir = tmp_path / "packages" / "guru-web" / "dist"
    assets_dir.mkdir(parents=True)
    (assets_dir / "index.html").write_text("<html><body>Guru Web</body></html>")
    runtime = build_web_runtime(
        project_root=tmp_path,
        assets_dir=assets_dir,
        enabled=True,
    )
    assert runtime.available is True
    assert runtime.assets_dir == assets_dir
```

- [ ] **Step 2: Run the targeted runtime tests**

Run:

```bash
uv run pytest packages/guru-server/tests/test_web_runtime.py -q
```

Expected: PASS once the runtime asset detection is final.

- [ ] **Step 3: Add repo-level ergonomics**

Add `.gitignore` entries:

```gitignore
packages/guru-web/dist/
packages/guru-web/node_modules/
```

Create `packages/guru-web/README.md` with:

```md
# guru-web

## Development

```bash
npm install
npm run dev
```

## Test

```bash
npm test
```

## Build

```bash
npm run build
```
```

- [ ] **Step 4: Run the frontend build and backend runtime checks**

Run:

```bash
cd packages/guru-web && npm run build
cd /Users/martinmacak/.codex/worktrees/d453/guru && uv run pytest packages/guru-server/tests/test_web_runtime.py packages/guru-server/tests/test_web_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/guru-web/README.md \
        packages/guru-web/package.json \
        packages/guru-server/src/guru_server/web_runtime.py \
        packages/guru-server/src/guru_server/app.py \
        packages/guru-server/tests/test_web_runtime.py \
        .gitignore \
        pyproject.toml
git commit -m "chore: finalize guru web runtime integration"
```

---

## Task 9: Final verification and acceptance sweep

**Files:**
- Modify as needed from previous tasks only if verification reveals real defects
- Verify: `packages/guru-web/src/**/*.test.tsx`
- Verify: `packages/guru-server/tests/test_web_*.py`
- Verify: `packages/guru-cli/tests/test_cli_server.py`

- [ ] **Step 1: Run the frontend test suite**

Run:

```bash
cd packages/guru-web && npm test
```

Expected: PASS.

- [ ] **Step 2: Run the focused Python verification suite**

Run:

```bash
uv run pytest \
  packages/guru-server/tests/test_web_runtime.py \
  packages/guru-server/tests/test_web_api.py \
  packages/guru-server/tests/test_web_open.py \
  packages/guru-server/tests/test_graph_api.py \
  packages/guru-server/tests/test_indexer_graph_integration.py \
  packages/guru-cli/tests/test_cli_server.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the broader workbench regression suite**

Run:

```bash
uv run pytest \
  packages/guru-cli/tests/test_tui_*.py \
  packages/guru-core/tests/test_graph_*.py \
  packages/guru-graph/tests/test_artifact_*.py \
  packages/guru-graph/tests/test_ingest_*.py \
  packages/guru-server/tests/test_graph_api.py \
  packages/guru-server/tests/test_indexer_graph_integration.py -q
```

Expected: PASS.

- [ ] **Step 4: Run lint**

Run:

```bash
make lint
```

Expected: PASS.

- [ ] **Step 5: Commit final polish if needed**

```bash
git add -A
git commit -m "test: verify knowledge workbench web ui integration"
```

Only create this commit if verification required real code/test updates. If all previous commits already cover the final state, skip this step.

---

## Self-review

### Spec coverage

- Web package and dev/prod split: Tasks 1, 2, 8
- `guru-server`-owned runtime web surface: Tasks 2, 3, 8
- explicit `web-open`: Task 3
- browser-first shell: Tasks 4, 5, 6
- parity-plus browser surfaces: Tasks 5, 6, 7
- React Flow graph with selection-centered model: Task 7
- degraded `web: unavailable` behavior: Task 2
- Vitest + RTL + jsdom only: Tasks 1, 4, 5, 6, 7, 9

No spec section is currently uncovered.

### Placeholder scan

- No `TBD` / `TODO`
- All tasks include files, tests, commands, and expected outcomes
- All referenced modules are introduced in the plan before use or in the same task

### Type consistency

- `web/boot` payload shape is consistent across Tasks 2 and 4
- `WebRuntime` fields are reused consistently
- frontend surfaces remain `Investigate`, `Graph`, `Query`, `Operate` throughout
