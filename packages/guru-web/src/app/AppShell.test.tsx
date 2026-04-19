import { describe, expect, it, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";

import { renderWithRouter } from "../test/render";
import { AppShell } from "./layout/AppShell";
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

  it("right pane toggles via button and persists in localStorage", () => {
    renderWithRouter(<AppShell />, { route: "/documents" });
    const toggle = screen.getByRole("button", { name: /toggle metadata/i });
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
