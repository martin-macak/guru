import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { GraphMetaPane } from "./GraphMetaPane";

describe("GraphMetaPane", () => {
  it("shows metadata for a selected document node", async () => {
    mockServer.use(
      http.get("/documents/a.md/metadata", () =>
        HttpResponse.json({
          lance: { path: "a.md", chunk_count: 1, token_count: 1, tags: [], ingested_at: null },
          graph: { node_id: "doc:a.md", degree: 3, links: [] },
        }),
      ),
    );
    renderWithRouter(<GraphMetaPane selectedId="doc:a.md" />);
    expect(await screen.findByText("LanceDB")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders empty state for federation root", () => {
    renderWithRouter(<GraphMetaPane selectedId="federation" />);
    expect(screen.getByText(/orientation anchor/i)).toBeInTheDocument();
  });

  it("renders KB summary for kb: node", () => {
    renderWithRouter(<GraphMetaPane selectedId="kb:local" />);
    expect(screen.getByText(/knowledge base/i)).toBeInTheDocument();
    expect(screen.getByText("local")).toBeInTheDocument();
  });
});
