import { render, screen } from "../test/render";
import { App } from "./App";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        project: { name: "guru", root: "/tmp/guru" },
        web: {
          enabled: true,
          available: true,
          url: "http://127.0.0.1:41773",
          reason: null,
          autoOpen: false,
        },
        graph: { enabled: true },
      }),
    })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

test("renders guru workbench shell after boot", async () => {
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Investigate" })).toBeInTheDocument();
  expect(screen.getByText("guru")).toBeInTheDocument();
  expect(screen.getByText("Knowledge Workbench")).toBeInTheDocument();
});
