import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { DocumentList } from "./DocumentList";
import { mockServer } from "../../test/msw";

describe("DocumentList", () => {
  it("renders items from GET /documents", async () => {
    mockServer.use(
      http.get("/documents", () =>
        HttpResponse.json([{ path: "a.md", title: "Alpha", excerpt: "a ex" }]),
      ),
    );
    renderWithRouter(<DocumentList onSelect={() => {}} selectedPath={null} />);
    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());
  });

  it("highlights the selected row", async () => {
    mockServer.use(
      http.get("/documents", () =>
        HttpResponse.json([{ path: "a.md", title: "Alpha", excerpt: "a ex" }]),
      ),
    );
    renderWithRouter(<DocumentList onSelect={() => {}} selectedPath="a.md" />);
    const row = await screen.findByRole("listitem", { name: /alpha/i });
    expect(row.getAttribute("aria-selected")).toBe("true");
  });
});
