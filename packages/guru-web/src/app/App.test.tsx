import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { AppBootstrap } from "./App";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppBootstrap />
    </QueryClientProvider>,
  );
}

test("shows loading state before boot resolves", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {
      // never resolves — keeps loading state
    })),
  );
  renderApp();
  expect(screen.getByText("Loading Guru…")).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test("shows error state when boot fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: false, status: 500 })),
  );
  renderApp();
  expect(await screen.findByText("Server unavailable")).toBeInTheDocument();
  vi.unstubAllGlobals();
});
