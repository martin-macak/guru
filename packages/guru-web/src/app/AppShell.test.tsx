import { render, screen, waitFor } from "../test/render";
import { App } from "./App";

const bootPayload = {
  project: { name: "guru", root: "/tmp/guru" },
  web: {
    enabled: true,
    available: true,
    url: "http://127.0.0.1:41773",
    reason: null,
    autoOpen: false,
  },
  graph: { enabled: true },
};

describe("App shell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => bootPayload,
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState({}, "", "/");
  });

  test("renders investigate as the default shell surface after boot loads", async () => {
    render(<App />);

    expect(screen.getByText("Loading Guru…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Investigate" })).toBeInTheDocument();
    expect(screen.getByText("guru")).toBeInTheDocument();
  });

  test("uses the current URL to choose the graph shell surface", async () => {
    window.history.replaceState({}, "", "/graph");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Graph" })).toBeInTheDocument();

    await waitFor(() => {
      expect(window.location.pathname).toBe("/graph");
    });
  });
});
