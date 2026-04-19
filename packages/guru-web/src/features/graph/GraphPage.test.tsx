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
});
