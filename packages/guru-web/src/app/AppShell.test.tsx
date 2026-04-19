import { describe, expect, it, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../test/render";
import { mockServer } from "../test/msw";
import { AppShell } from "./layout/AppShell";
import { DocumentsPage } from "../features/documents/DocumentsPage";
import { useWorkbench } from "../lib/state/workbench";

// Provide a minimal localStorage mock for environments that don't fully support it
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

beforeEach(() => {
  vi.stubGlobal("localStorage", localStorageMock);
  localStorageMock.clear();
  // Reset store to defaults
  useWorkbench.setState({
    rightPaneOpen: { documents: true, graph: true, status: false },
    surface: "documents",
  });
});

describe("AppShell", () => {
  it("renders three menu items", () => {
    renderWithRouter(<AppShell />);
    expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Graph" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Status" })).toBeInTheDocument();
  });

  it("does not render legacy Investigate/Query/Operate", () => {
    renderWithRouter(<AppShell />);
    expect(screen.queryByText("Investigate")).toBeNull();
    expect(screen.queryByText("Query")).toBeNull();
    expect(screen.queryByText("Operate")).toBeNull();
  });

  it("right pane toggles via button and persists in localStorage", async () => {
    // AppShell doesn't render its own RightPane — surfaces do. Mount
    // DocumentsPage via the Outlet so the metadata pane appears.
    mockServer.use(http.get("/documents", () => HttpResponse.json([])));
    renderWithRouter(
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route path="documents" element={<DocumentsPage />} />
        </Route>
      </Routes>,
      { route: "/documents" },
    );
    const toggle = await screen.findByRole("button", { name: /toggle metadata/i });
    fireEvent.click(toggle);
    expect(
      JSON.parse(localStorage.getItem("guru.workbench.paneState") || "{}").documents,
    ).toBe(false);
  });

  it("main area has no max-width constraint", () => {
    const { container } = renderWithRouter(<AppShell />);
    const main = container.querySelector("[data-surface-main]");
    expect(main).toBeTruthy();
    const cs = getComputedStyle(main!);
    expect(cs.maxWidth === "none" || cs.maxWidth === "" || cs.maxWidth.endsWith("%")).toBeTruthy();
  });
});
