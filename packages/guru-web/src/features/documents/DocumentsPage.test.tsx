import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { DocumentsPage } from "./DocumentsPage";

/** Render DocumentsPage inside a Routes tree so useParams works correctly. */
function renderDocumentsPage(route = "/documents") {
  return renderWithRouter(
    <Routes>
      <Route path="documents" element={<DocumentsPage />} />
      <Route path="documents/*" element={<DocumentsPage />} />
    </Routes>,
    { route },
  );
}

describe("DocumentsPage", () => {
  it("shows list, clicking a row shows detail, metadata pane visible", async () => {
    mockServer.use(
      http.get("/documents", () =>
        HttpResponse.json([{ path: "a.md", title: "Alpha", excerpt: "a" }]),
      ),
      http.get("/documents/a.md", () =>
        HttpResponse.json({ path: "a.md", title: "Alpha", content: "hello" }),
      ),
      http.get("/documents/a.md/metadata", () =>
        HttpResponse.json({
          lance: { path: "a.md", chunk_count: 1, token_count: 1, tags: [], ingested_at: null },
          graph: null,
        }),
      ),
    );
    renderDocumentsPage("/documents");
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByText("Alpha"));
    await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
    expect(screen.getByText("LanceDB")).toBeInTheDocument();
  });

  it("search replaces the list", async () => {
    mockServer.use(
      http.get("/documents", () =>
        HttpResponse.json([{ path: "a.md", title: "Alpha", excerpt: "a" }]),
      ),
      http.post("/documents/search", () =>
        HttpResponse.json({ hits: [{ path: "b.md", title: "Beta", excerpt: "hit", score: 0.9 }] }),
      ),
    );
    renderDocumentsPage("/documents");
    await screen.findByText("Alpha");
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "x" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByText("Beta")).toBeInTheDocument());
    expect(screen.queryByText("Alpha")).toBeNull();
  });

  it("shows placeholder when no document is selected", async () => {
    mockServer.use(http.get("/documents", () => HttpResponse.json([])));
    renderDocumentsPage("/documents");
    const placeholders = await screen.findAllByText(/select a document/i);
    expect(placeholders.length).toBeGreaterThanOrEqual(1);
  });
});
