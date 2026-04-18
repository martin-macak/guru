import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen } from "../../test/render";
import { AppShell } from "../../app/layout/AppShell";
import { WorkbenchProvider } from "../../lib/state/workbench";
import { InvestigatePage } from "./InvestigatePage";

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

function renderWithWorkbench(ui: ReactElement) {
  return render(
    <MemoryRouter initialEntries={["/investigate"]}>
      <WorkbenchProvider boot={bootPayload} initialSurface="investigate">
        {ui}
      </WorkbenchProvider>
    </MemoryRouter>,
  );
}

test("renders search box and result panels", () => {
  renderWithWorkbench(<InvestigatePage />);

  expect(screen.getByPlaceholderText("Search knowledge base")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Results" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Inspector" })).toBeInTheDocument();
  expect(screen.getByText("Select a document or artifact to inspect its metadata.")).toBeInTheDocument();
});

test("keeps knowledge tree and inspector in sync with shared selection", () => {
  renderWithWorkbench(<AppShell />);

  expect(screen.getByRole("heading", { name: "Knowledge Tree" })).toBeInTheDocument();
  expect(screen.getAllByRole("heading", { name: "Inspector" })).toHaveLength(2);

  fireEvent.click(screen.getByRole("button", { name: /^Artifact Graph Plan document$/i }));
  expect(screen.getByText("Document")).toBeInTheDocument();
  expect(screen.getByText("docs/superpowers/plans/2026-04-18-artifact-graph-knowledge-base.md")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /^Graph neighbors route artifact$/i }));
  expect(screen.getByText("Artifact")).toBeInTheDocument();
  expect(screen.getByText("packages/guru-server/src/guru_server/api/graph.py")).toBeInTheDocument();
});
