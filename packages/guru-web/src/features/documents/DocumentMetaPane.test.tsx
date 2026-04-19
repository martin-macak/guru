import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { DocumentMetaPane } from "./DocumentMetaPane";

describe("DocumentMetaPane", () => {
  it("shows LanceDB and Graph sections when graph enabled", async () => {
    mockServer.use(
      http.get("/documents/a.md/metadata", () =>
        HttpResponse.json({
          lance: {
            path: "a.md",
            chunk_count: 3,
            token_count: 42,
            tags: ["foo"],
            ingested_at: "2026-04-19T00:00:00Z",
          },
          graph: {
            node_id: "doc:a.md",
            degree: 2,
            links: [{ kind: "DEPENDS_ON", target: "b.md" }],
          },
        }),
      ),
    );
    renderWithRouter(<DocumentMetaPane path="a.md" graphEnabled={true} />);
    expect(await screen.findByText("LanceDB")).toBeInTheDocument();
    expect(screen.getByText("Graph")).toBeInTheDocument();
    expect(screen.getByText("chunks")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("hides Graph section when graph disabled", async () => {
    mockServer.use(
      http.get("/documents/a.md/metadata", () =>
        HttpResponse.json({
          lance: { path: "a.md", chunk_count: 1, token_count: 1, tags: [], ingested_at: null },
          graph: null,
        }),
      ),
    );
    renderWithRouter(<DocumentMetaPane path="a.md" graphEnabled={false} />);
    await screen.findByText("LanceDB");
    expect(screen.queryByText("Graph")).toBeNull();
  });
});
