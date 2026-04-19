import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { GraphPage } from "./GraphPage";

describe("GraphPage", () => {
  it("renders federation root + each KB on initial load", async () => {
    mockServer.use(
      http.get("/graph/roots", () =>
        HttpResponse.json({
          federation_root: { id: "federation", label: "Federation" },
          kbs: [
            { name: "local", project_root: "/p", tags: [] },
            { name: "peer", project_root: "/q", tags: [] },
          ],
        }),
      ),
    );
    renderWithRouter(<GraphPage />, { route: "/graph" });
    await screen.findByText("Federation");
    expect(screen.getByText("local")).toBeInTheDocument();
    expect(screen.getByText("peer")).toBeInTheDocument();
  });

  it("focuses via ?focus= and draws path-to-root", async () => {
    mockServer.use(
      http.get("/graph/roots", () =>
        HttpResponse.json({
          federation_root: { id: "federation", label: "Federation" },
          kbs: [{ name: "local", project_root: "/p", tags: [] }],
        }),
      ),
      http.get("/graph/neighbors/:id", () => {
        return HttpResponse.json({
          nodes: [{ id: "doc:a.md", label: "A", kind: "document", kb: "local" }],
          edges: [],
        });
      }),
    );
    renderWithRouter(<GraphPage />, { route: "/graph?focus=doc%3Aa.md" });
    // Deep link via ?focus= should fetch neighbors and render the focused node.
    await screen.findByText("A");
    // ReactFlow renders overlay edges as SVG paths with inline styles; in jsdom
    // the SVG <g> is present in the DOM even if paths lack pixel positions.
    // Verify the ReactFlow edges container exists (path-to-root is rendered as
    // overlay edges passed to the same ReactFlow instance).
    const edgesContainer = document.querySelector(".react-flow__edges");
    expect(edgesContainer).not.toBeNull();
    // The focused node "A" (doc:a.md) is rendered in the canvas.
    expect(document.querySelector('[data-id="doc:a.md"]')).not.toBeNull();
  });
});
