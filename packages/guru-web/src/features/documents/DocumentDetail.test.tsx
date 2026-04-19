import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithRouter } from "../../test/render";
import { mockServer } from "../../test/msw";
import { DocumentDetail } from "./DocumentDetail";

describe("DocumentDetail", () => {
  it("renders markdown content", async () => {
    mockServer.use(
      http.get("/documents/a.md", () =>
        HttpResponse.json({ path: "a.md", title: "A", content: "# Hello\n\n**world**" }),
      ),
    );
    renderWithRouter(<DocumentDetail path="a.md" />);
    expect(await screen.findByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("world").tagName).toBe("STRONG");
  });

  it("Go to graph button navigates and focuses node", async () => {
    mockServer.use(
      http.get("/documents/a.md", () =>
        HttpResponse.json({ path: "a.md", title: "A", content: "x" }),
      ),
    );
    const { router } = renderWithRouter(<DocumentDetail path="a.md" />);
    fireEvent.click(await screen.findByRole("button", { name: /go to graph/i }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/graph"));
    expect(router.state.location.search).toBe("?focus=doc%3Aa.md");
  });
});
